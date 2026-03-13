# Log things

## Log merger

will merge 2 logs in one

```
python mergelogs.py log1.wpilog log2.wpilog output.wpilog
```

## Log cropper

it will crop the log files based on the rsl state and leave 5 seconds before and after the match
it will output in a file named <original name>-cropped.wpilog

```
python croplogs.py log1.wpilog log2.wpilog ...
```

if you want to edit the padding (time before and after the match), you can use these 2 command line arguments

- `--start-pad`
- `--end-pad`

for example, `python croplogs.py log1.wpilog --start-pad=3`
