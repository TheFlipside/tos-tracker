# TOS-tracker

From a list of sources, URLs are read, the content obtained and stored locally.
By making use of version control systems, changes can be made visible easily.

## Usage

```sh
pip install -r requirements.txt

python3 -m playwright install chromium

python3 fetch.py
```

## Automatic script

To periodically fetch the sources, add a cronjob which executes the script.

```sh
0 6 * * * /path/to/tos-tracker/update.sh
```
