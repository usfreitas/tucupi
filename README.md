# Tucupi
## An interactive tool to manage and delete duplicated files

This program is very alpha at the moment, although it can be useful. It looks 
for repeated (or duplicated) files in the file system and presents a (hopefully) 
easy to use interface to help the user decide which files to keep and which to delete.

It is named after a Brazilian sauce made from wild manioc roots.
The [sauce](https://en.wikipedia.org/wiki/Tucupi) can be poisonous if not prepared
correctly. This program can also be dangerous as it deals with deleting files. 

##Motivation
While finding identical files is simple, although sometimes slow, deciding what to
do with the repeated files is not. Tucupi aims to help the user in locating duplicated 
files and in selecting which to keep and which to delete. 

## How to use

File->Open lets you choose a folder to analyze. It then runs a `find` in the selected
folder looking for regular files. The list of files together with their size is then 
read and analyzed. Files that have the same size as another have their md5 sum 
computed with `md5sum`. A file is considered repeated if another with same size and 
md5sum is found. 

Scanning a large file tree is slow. After finishing the analysis of the `find` output,
Tucupi starts md5 computation. Md5 are computed from the largest file downwards. This 
process can be interrupted with the "stop" button. This allows the user to select 
another folder to scan. Once this other folder was scanned with `find`, a click on the 
"play" button restarts the md5 computation with the updated list of files. No work 
is lost and the md5sum is not computed more than once for each file. Multiple different 
folders can be selected this way.

The maximum file size to be scanned can be set with the slider on the bottom left corner.
Files grater than this size won't have their md5sum computed. This can be used to 
speed up an analysis on a folder where Tucupi was already executed and md5 where computed
down to a certain size and than stopped. By ignoring files larger than this size, the
analysis can start again more or less where it stopped.

The interface is roughly divided in two panels. The left panel list the repeated 
files found. Files are listed by size and md5sum. Under each entry are the paths to 
the individual copies. The user can select individual files for deletion using the
check box next to each file path. To avoid losing data, selection of all copies is 
impossible. At least one copy of each file always remains unselected. 

A double click on a file path open that path on the right panel. The right panel 
shows a part of the scanned file tree. It shows the contents of a folder, its files
and subfolders. "Rep. Size" informs about the space occupied by repeated files, either
by the file itself or by the files in the subfolder. Also listed are the total number 
of files ("Number"), the number of duplicated files ("Repeated"), the number of files 
marked for deletion, the number of files marked as "keep", and the total size occupied 
by the file or subfolder.

Selecting one or more files or subfolders and right-clicking opens up a menu. 
"Mark all repeated" will then try to mark all repeated files in the selected subfolders
recursively and all selected files that are repeated. As with the left panel, 
this won't mark all the copies of a file for deletion and will leave at least one 
copy unmarked. Also only repeated files will be marked. "Unmark all repeated" will 
remove the mark for deletion recursively from all the selected files and subfolders.
"Keep all files" will unmark recursively all files. It will also prevent theses files
from being marked for deletion by marking them "for keep". This gives the user more 
freedom to choose which files to delete and which to keep. For instance, the user 
can "keep" one or more subfolders and then "mark all repeated" on the parent folder, 
thus choosing which copies to keep.


The buttons "Up", "Forward" and "Backward" will control navigation of the right panel.
Right now only the "Up" button works. Double clicking on a subfolder shows that folder 
on the right panel. Double clicking on a file select that file on the _left_ panel.

## Deleting repeated files

Clicking on the "Delete marked" will open a file dialog. Here the user should enter a 
file where a log of the actions will be written. This is a XML file listing the sizes, 
and md5sums of marked files, the paths of deleted files and of files kept. In the 
future this file should allow the automatic recreation of deleted files, but it is 
readable enough now to allow this operation by hand.

As of now, the code to directly delete the files is disabled (remember, this is alpha!).
Instead, a file named "del_out" is created on the same folder of Tucupi. This files
contains the paths of the files marked for deletion, separated by the null character.
The user should verify that this list is OK before deleting the files, which can be 
made using xargs:

    $ cat del_out | xargs -0 rm


## How to run (what is needed)

Just run `tucupi.py` from its own folder. The program needs Python 3.4, Numpy, GTK+ 3
and its python bindings, as well as `find`, `md5sum` and `xargs`. Tucupi is developed
for GNU/Linux systems although it might work in other environments provided the 
requirements are met.
