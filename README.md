# ifmap.py -- the index generator tool for the IF Archive

- Copyright 2017 by the Interactive Fiction Technology Foundation
- Distributed under the MIT license
- Created by Andrew Plotkin <erkyrath@eblong.com>

This program has one core task: to look through all the files in the IF Archive, combine that with the contents of the Master-Index file, and generate all the index.html files in the indexes subdirectory.

(The Master-Index file is created by sewing together all the Index files in all the directories of the Archive. A different script does that job.)

## Arguments

In normal Archive operation, this is invoked from the build-indexes script.

- --index FILE: pathname of Master-Index. (Normally /var/ifarchive/htdocs/if-archive/Master-Index.)
- --src DIR: Pathname of the directory full of HTML templates which control the appearance of the index files. (Normally /var/ifarchive/lib/ifmap.)
- --dest DIR: Pathname of the indexes directory, where the index files are written. (Normally /var/ifarchive/htdocs/indexes.)
- --tree DIR: Pathname of the root directory which the Archive serves. (Normally /var/ifarchive/htdocs.)
- --v: If set, print verbose output.
- --exclude: If set, files without index entries are excluded from index listings. (Normally *not* set.)

## Testing

Type `python3 tests.py` to run tests on the low-level string-escaping and templating code. It's not an end-to-end test. For that, you pretty much have to run the script and see what it generates. Compare it to what the previous version generated, that's a good trick.

## History

I wrote the first version of this program in 1999-ish. It was built around the original Index files, which were hand-written by Volker Blasius (the original Archive curator) for human consumption. Their format was not particularly convenient for parsing, but I parsed them anyway.

I wrote the original program in C because it was portable and I didn't know Python or Perl yet. C is a terrible language for this sort of thing, of course -- I started by implementing my own hash tables. And escaping strings for HTML? Yuck.

I finally ported it all to Python in July of 2017. It's now got less than half the lines of code, it's infinitely more readable, and it's faster. (Not because Python is faster, but because I added an MD5-caching feature.)

