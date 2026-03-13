# Log things

## Log merger

will merge 2 logs in one

```
python mergelogs.py -o output.wpilog log1.wpilog log2.wpilog
```

by default, it leaves a 1 second gap between logs
you can edit it using the `--gap=...` argument
for example, `python mergelogs.py --gap=2000 -o output.wpilog log1.wpilog log2.wpilog` to have a 2 second gap

## Log cropper

it will crop the log files based on the rsl state and leave 5 seconds before and after the match
it will output in a file named <original name>-cropped.wpilog

```
python croplogs.py log1.wpilog log2.wpilog ...
```

if you want to edit the padding (time before and after the match), you can use these 2 command line arguments

- `--start-pad`
- `--end-pad`

for example, `python croplogs.py log1.wpilog --start-pad=3000` to have 3 seconds instead of 5 before the match
