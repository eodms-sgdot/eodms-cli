$scriptpath = $MyInvocation.MyCommand.Path
$dir = Split-Path $scriptpath
python $dir/eodms_cli.py $args

pause