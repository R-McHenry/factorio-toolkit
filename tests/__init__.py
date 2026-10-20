import os

# The tests never use the game link, even when run on the game host with FK_LINK=on exported.
os.environ["FK_LINK"] = "off"
