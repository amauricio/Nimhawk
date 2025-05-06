from os import setCurrentDir, normalizePath
from strutils import join

# Change the current working directory
proc cd*(args : seq[string]) : string =
    var newDir = args.join(obf(" "))
    if newDir == "":
        result = obf("Invalid number of arguments received. Usage: 'cd [directory]'.")
    else:
        setCurrentDir(newDir)
        result = obf("Changed working directory to '") & newDir & obf("'.")