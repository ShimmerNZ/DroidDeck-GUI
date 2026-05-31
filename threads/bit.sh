distrobox enter droiddeckapp -- bash -c "
source ~/droiddeck_env/bin/activate
python3 -c \"
import bitsteam
from bitsteam import SteamDeck

try:
    print('version:', bitsteam.__version__)
except:
    print('no version')

print()
print('Class methods:')
for n in dir(SteamDeck):
    if not n.startswith('__'):
        print(' ', n)

try:
    deck = SteamDeck()
    print()
    print('Instance methods:')
    for n in dir(deck):
        if not n.startswith('__'):
            print(' ', n)
    deck.close()
except Exception as e:
    print('error:', e)
\" > ~/DroidDeck/bitsteam_api.txt 2>&1
echo done
"