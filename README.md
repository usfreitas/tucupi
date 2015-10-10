# tucupi
## An interactive tool to manage and delete duplicated files

This program is very alpha at the moment, although it can be useful. It looks 
for repeated (or duplicated) files in the file system and presents a (hopefully) 
easy to use interface to help the user decide which files to keep and which to delete.

It is named after a Brazilian sauce made from wild manioc roots.
The [sauce](https://en.wikipedia.org/wiki/Tucupi) can be poisonous if not prepared
correctly. This program can also be dangerous as it deals with deleting files. 

## How to use

File->Open lets you choose a folder to analyze. It then runs a "find" in the selected
folder looking for regular files. The list of files together with their size is then 
read and analyzed. Files that have the same size as another have their md5 sum 
computed with "md5sum". A file is considered repeated if another with same size and 
md5sum is found. 

Scanning a large file tree is slow. After finishing the analysis of the "find" output,
tucupi starts md5 computation. Progress messages are written (for now) on the terminal.
Md5 are computed from the largest file downwards. This process can be interrupted with
the "stop" button. This allows the user to select another folder to scan. Once the 
initial scan is finished, a click on the "play" button restarts the md5 computation 
with the updated list of files. No work is lost and the md5sum is not computed more
than once for each file. Multiple different folders can be selected this way.

The interface is roughly divided in two panels. The left panel list the repeated 
files found. Files are listed by size and md5sum. Under each entry are the paths to 
the individual copies. The user can select individual files for deletion using the
check box next to each file path. To avoid losing data, selection of all copies is 
impossible. At least one copy of each file remains unselected. 

A double click on a file path open that path on the right panel. The right panel 
shows a part of the scanned file tree. It shows the contents of a folder, its files
and subfolders. "Rep. Size" informs about the space occupied by repeated files, either
the file itself or in the subfolder. Also listed are the total number of files "Number",
the number of duplicated files "Repeated", the number of files marked for deletion and
the total size occupied by the file or subfolder.

Selecting one or more files or subfolders and right-clicking opens up a menu. 
"Mark all repeated" will then try to mark all repeated files in the selected subfolders
(recursively) and all selected files that are repeated. "Unmark all repeated" will
unmark the files in the same way. As with the left panel, this won't mark all the copies
of a file.

The buttons "Up", "Forward" and "Backward" will control navigation of the right panel.
Right now only the "Up" button works. Double clicking in a subfolder shows that folder 
on the right panel.

## Deleting repeated files

Clicking on the "Delete marked" will open a file dialog. Here the user should enter a 
file where a log of the actions will be written. This is a XML file listing the sizes, 
and md5sums of selected files, the paths of deleted files and of files kept. In the 
future this file should allow the automatic recreation of deleted files, but it is 
readable enough now to allow this operation by hand.

As of now, the code to directly delete the files is disabled (remember, this is alpha!).
Instead, a file named "del_out" is created on the same folder of tucupi. This files
contains the paths of the selected files, separated by the null character. The user 
should verify that this list is OK before deleting the files, which can be made using
xargs:
$ cat del_out | xargs -0 rm


## Installation

Just run tucupi from its own folder. The program needs Python 3.4, Numpy, GTK+ 3, as
well as find, md5sum and xargs.
