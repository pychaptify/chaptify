# chaptify
Requirements:
* Spotify API account
* Conda (or Conda-like) Environment manager (I use [miniforge](#https://github.com/conda-forge/miniforge)
* [ffmpeg](#https://www.ffmpeg.org/) ([I used brew to install](#https://formulae.brew.sh/formula/ffmpeg))

## Setup 
### Spotify API Account
(This is all free)
1. Set up a developer account with [Spotify API](#https://developer.spotify.com/)
2. Create an "app" under your account
3. Once you've set up an app, go into the app's dashboard/settings
4. Under the "Basic Information" tab, you'll find your Client ID & click "View client secret" to reveal your Client Secret, save those you'll need them later.  

### Commandline Setup 
1. In the location you'd like to place this app run:
```
mkdir chaptify
cd chaptify
git clone https://github.com/srobe/fluid_react.git
```
2. Now, build the conda environment
```
conda env create --file=environment.yaml
```
4. Add your environmental variables
With vim:
```
vim .env
```
Press i to enter insert mode.
Paste the following content:
```
CLIENT_ID={replace with your client id code}
CLIENT_SECRET={replace with your client secret code}
```
Press Esc, type :wq, and hit Enter to save and exit.

## Running the code
1. Make sure the conda env is activated:
```
conda activate chaptify
```
2. Make sure the m4b files have the proper title/artist metadata and/OR make the file name
[authorfirstname authorlastname] - [Short Book Title].m4b
e.g.
"Octavia E. Butler - Parable of the Sower.m4b"
"Nathan Hill - The Nix.m4b"
"Diana Wynne Jones - Howl's Moving Castle.m4b"
2. Run the code:
```
python chaptify.py -f "Diana Wynne Jones - Howl's Moving Castle.m4b"
```
