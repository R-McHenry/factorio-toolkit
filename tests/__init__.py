import os

# The tests never use the game link, even when run on the game host with FK_LINK=on exported.
os.environ["FK_LINK"] = "off"
# 47-cleanpaste: a missing answer file is the tests' fake game, not a slow share: no wait
# (link.FILE_WAIT, 180 s since 3.2.1, made every such test sit out the whole wait)
os.environ.setdefault("FK_FILE_WAIT", "0")
