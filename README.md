# Log things

## Log merger

will merge 2 logs in one

```
python mergelogs.py log1.wpilog log2.wpilog output.wpilog
```

## Log cropper

for now, it only crops at the start (not the end)
It will output in a file named <original name>-cropped.wpilog

```
python croplogs.py log1.wpilog log2.wpilog ...
```
