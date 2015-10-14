#!/usr/bin/env python3

#Copyright 2015 Ubiratan S. Freitas
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
# 
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.




import threading

from gi.repository import Gtk,GObject,GLib

import sys
import subprocess as sb
import numpy as np

import math

from xml.dom.minidom import getDOMImplementation
impl = getDOMImplementation()


class DelOutput(object):
    def __init__(self):
        self.buffer = b''
    def add_arg(self,arg):
        self.buffer = self.buffer + arg + b'\x00'
    def clear(self):
        self.buffer = b''

del_out = DelOutput()


def human_size(s,precision = 2):
    s = int(s)
    negative = False
    if s < 0: negative = True
    s = abs(s)
    if s == 0:
        return '0B'
    pre_val = math.floor(math.log(s)/math.log(1024))
    bin_prefix = ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi', 'Yi']
    pre_val = min(pre_val, 8)
    if pre_val > 0:
        return '{0:.{prec}f}{1}B'.format(s/(1024**pre_val),bin_prefix[pre_val], prec = precision)
    else:
        return '{0}B'.format(s)

def col_human(tree_column, cell, tree_model, titer, col):
    size = tree_model[titer][col]
    cell.set_property('text',human_size(size))



class Finder(threading.Thread):
    def __init__(self,path):
        threading.Thread.__init__(self)
        self.result = None
        self.path = path

    def run(self):
        try:
            self.result = sb.check_output(['find', self.path, '-type', 'f','-printf', '%s %h/%f\\0'])
        except sb.CalledProcessError as err:
            print('Error in find!')
            self.result = err.output



class FNode(object):
    def __init__(self,fpath,size):
        self.fpath = fpath
        self.md5 = None
        self.size = size
        self.marked = False
        self.repeated = False
    
    def mark(self,rep_file):
        if not self.marked and self.repeated:
            rep_file.toggle_mark(self)


class RepFile(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.size_md5 = {}
        self.repeated = set()
        self.ts_contents = []
        
    def add_fn(self,fn):
        if fn.md5 is None:
            raise ValueError('md5sum not present')
        key = (fn.size,fn.md5)
        
        with self.lock:
            if key not in self.size_md5:
                self.size_md5[key] = [fn]
            else:
                fn.repeated = True
                self.size_md5[key].append(fn)
                self.repeated.add(key)
                if len(self.size_md5[key]) == 2:
                    self.size_md5[key][0].repeated = True
        

    def add_empty(self,empty_files):
        with self.lock:
            key = (0, b'empty_file')
            self.repeated.add(key)
            self.size_md5[key] = empty_files.copy()
            for fn in self.size_md5[key]:
                fn.md5 = key[1]
                fn.repeated = True

    def update_model(self,ts):
        assert len(ts) == len(self.repeated), 'different number of rows in treestore'
        with self.lock:
            print('update_model')
            main_iter = ts.get_iter_first()
            while main_iter != None:
                main_row = ts[main_iter]
                key = self.ts_contents[main_row[-1]]
                files = self.size_md5[key]
                unmarked = [fn for fn in files if not fn.marked]
                if len(unmarked) == 1:
                    main_row[2] = True
                else:
                    main_row[2] = False
                if main_row[3]:
                    nchildren = ts.iter_n_children(main_iter)
                    assert len(files) == nchildren, 'different number of files in treestore'
                    for k in range(nchildren):
                        child = ts[ts.iter_nth_child(main_iter,k)]
                        fn = files[k]
                        assert k == child[-1], 'files out of order in treestore'
                        child[2] = fn.marked
                main_iter = ts.iter_next(main_iter)
            
    def add_children(self,ts,tpath):
        main_row = ts[tpath]
        main_iter = ts.get_iter(tpath)
        key = self.ts_contents[main_row[-1]]
        files = self.size_md5[key]
        main_row[3] = True
        for kk, f in enumerate(files):
            ts.append(main_iter,[f.fpath.decode(errors='replace'), files[0].size, f.marked,False,kk])

    def is_processed(self,ind):
        key = self.ts_contents[ind]
        files = self.size_md5[key]
        unmarked = [fn for fn in files if not fn.marked]
        return len(unmarked) == 1
    
    def append_to_model(self,ts):
        with self.lock:
            main_iter = ts.get_iter_first()
            while main_iter != None:
                main_row = ts[main_iter]
                if main_row[3]:
                    key = self.ts_contents[main_row[-1]]
                    files = self.size_md5[key]
                    nchildren = ts.iter_n_children(main_iter)
                    for k in range(len(files)-nchildren):
                        f = files[nchildren+k]
                        ts.append(main_iter,[f.fpath.decode(errors='replace'), files[0].size, f.marked,False,nchildren+k])
                
                main_iter = ts.iter_next(main_iter)
            
            copied = set(self.ts_contents)
            for k in self.repeated - copied:
                files = self.size_md5[k]
                self.ts_contents.append(k)
                main_row = ts.append(None,[k[1].decode(errors='replace'), k[0] ,False,False, len(self.ts_contents) -1 ])
        print('append_to_model lock released')
    
    def getfn(self,ts,tpath):
        assert tpath.get_depth() == 2, 'tree path not from a file'
        with self.lock:
            main_row = ts[tpath[0]]
            key = self.ts_contents[main_row[-1]]
            files = self.size_md5[key]
            child = ts[tpath]
            return files[child[-1]]
    
    def toggle_mark(self,fn):
        key = (fn.size,fn.md5)
        fl = self.size_md5[key]
        ind = fl.index(fn)
        if fn.marked:
            fn.marked = False
            return True
        else:
            allmarked = True
            with self.lock:
                for k in fl:
                    if k is not fn:
                        allmarked = allmarked and k.marked
            if allmarked:
                return False
            else:
                fn.marked = True
                return True

    def to_xmlfile(self,fname):
        with impl.createDocument(None, "data", None) as xmldoc:
            root = xmldoc.documentElement
            with self.lock:
                for key in sorted(self.repeated,reverse=True):
                    fn_list = self.size_md5[key]
                    marked = list(filter(lambda x:x.marked,fn_list))
                    if len(marked) > 0:
                        f = xmldoc.createElement('file')
                        size = xmldoc.createAttribute('size')
                        size.value = str(key[0])
                        md5 = xmldoc.createAttribute('md5')
                        md5.value = key[1].decode(errors='replace')
                        f.setAttributeNode(md5)
                        f.setAttributeNode(size)
                        for fn in fn_list:
                            if fn.marked:
                                ff = xmldoc.createElement('deleted')
                            else:
                                ff = xmldoc.createElement('kept')
                            fpath = xmldoc.createTextNode(fn.fpath.decode(errors='replace'))
                            ff.appendChild(fpath)
                            f.appendChild(ff)
                        root.appendChild(f)
            f = open(fname,'wt')
            f.write(xmldoc.toprettyxml(indent="    "))
        
                        




class FSTree(object):
    def __init__(self,path = b''):
        self.branches = {}
        self.leaves = {}
        self.path = path
        self.shown = None
        self.aggr_attrib = np.zeros((5,),dtype = np.int64)
        
    def add_leaf(self,leaf_path,leaf_attib):
        p = leaf_path.partition(b'/')
        if p[1] == b'': 
            #Leaf
            if p[0] not in self.leaves:
                self.leaves[p[0]] = leaf_attib
                return True
            else:
                return False
        elif len(p[0]) == 0:
            #root node
            return self.add_leaf(p[2],leaf_attib)
        else:
            assert len(p[2]) >0, 'Empty leaf inserted'
            if p[0] not in self.branches:
                self.branches[p[0]] = FSTree(path = self.path + b'/' + p[0])
            return self.branches[p[0]].add_leaf(p[2],leaf_attib)

    
    def compute_aggr(self):
        self.aggr_attrib[:] = 0
        for bname,br in self.branches.items():
            br.compute_aggr()
            self.aggr_attrib[:] = self.aggr_attrib + br.aggr_attrib

        for lname,lf in self.leaves.items():
            self.aggr_attrib[:] = self.aggr_attrib + np.array([ 1, lf.size ,int(lf.repeated),
                int(lf.repeated)*lf.size, int(lf.marked)],dtype=np.int64)
            
            
    def get_branch(self,branch_path):
        p = branch_path.partition(b'/')
        if  len(p[0]) == 0:
            #root node
            return self.get_branch(p[2])
        elif p[1] == b'' or p[2] == b'': 
            return self.branches[p[0]]
        
        else:
            return self.branches[p[0]].get_branch(p[2])

    def get_leaf(self,leaf_path):
        p = leaf_path.partition(b'/')
        if  len(p[0]) == 0:
            #root node
            return self.get_leaf(p[2])
        elif p[1] == b'': 
            #Leaf
            return self.leaves[p[0]]
        else:
            assert len(p[2]) >0, 'Trying to get an empty leaf'
            return self.branches[p[0]].get_leaf(p[2])

    def get_index(self,ind):
        return self.shown[ind]

    
    def copy_to_model(self,list_store):
        ncol = list_store.get_n_columns
        list_store.clear()
        self.shown = []
        ind = 0
        for br_name,br in self.branches.items():
            row = ['folder', br_name.decode(errors='replace')]
            row.extend(br.aggr_attrib.tolist())
            row.append(ind)
            list_store.append(row)
            self.shown.append(br)
            ind = ind +1
        for lf_name,att in self.leaves.items():
            row = ['gtk-file',lf_name.decode(errors='replace')]
            row.extend([ 1, att.size ,int(att.repeated),int(att.repeated)*att.size,int(att.marked),ind])
            list_store.append(row)
            self.shown.append(att)
            ind = ind + 1
    
    def get_keys(self,keys = None):
        if keys is None:
            keys = set()

        for br in self.branches.values():
            br.get_keys(keys)
        for fn in self.leaves.values():
            if fn.md5 is not None:
                keys.add((fn.size,fn.md5))
        return keys
        
    def mark_all(self,rep_file):
        for fn in self.leaves.values():
            fn.mark(rep_file)
        for br in self.branches.values():
            br.mark_all(rep_file)

    def unmark_all(self):
        for fn in self.leaves.values():
            fn.marked = False
        for br in self.branches.values():
            br.unmark_all()

    
    def delete_marked(self):
        for br in self.branches.values():
            br.delete_marked()
            #TODO add directory removal
        for fn in self.leaves.values():
            if fn.marked:
                delete_fnode(fn)
        
        
    def print(self,fill = ''):
        first = True
        for bname,br in self.branches.items():
            if not first:
                print(fill+'',end='')
            else:
                first = False
            print('/'+bname,end='')
            br.print(fill+('+')*(len(bname)+1))
            
        for lname,lf in self.leaves.items():
            if not first:
                print(fill+'',end='')
            else:
                first = False
            print('/'+lname)


def make_fstree(find_output, tree_root, sizes , same_size):
    files = find_output.split(b'\x00')
    
    
    for k in files[:-1]:
        resp = k.partition(b' ')
        s = int(resp[0])
        file_node = FNode(resp[2],s)
        if tree_root.add_leaf(resp[2],file_node):
            #Ignore a file already added
            if s in sizes:
                sizes[s].append(file_node)
                same_size.add(s)
            else:
                sizes[s] = [file_node]

    tree_root.compute_aggr()
    #print('{} files with repeated size'.format(sum([len(sizes[k]) for k in same_size.keys()])))
    return tree_root, sizes, same_size

    
def compute_md5(fnlist,rep_files):

    while(len(fnlist)>0):
        fn = fnlist.pop(0)
        if fn.md5 is None:
            try:
                md5 = sb.check_output(['md5sum',fn.fpath])
                md5 = md5[:32]
            except sb.CalledProcessError:
                md5 = b'Not found'
            
            fn.md5 = md5
            rep_files.add_fn(fn)

def delete_fnode(fnode):
    del_out.add_arg(fnode.fpath)
    #cmd = ['ls','-l', fnode.fpath]
    #ret = sb.call(cmd)
    return True
        
 
        
class UI(object):
    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file('tucupi.glade')
        self.win = self.builder.get_object('main_window')
        self.hbox = self.builder.get_object('hbox')
        self.path_label = self.builder.get_object('path_label')
        self.files_label = self.builder.get_object('files_label')
        self.popup_menu = self.builder.get_object('popup_menu')
        self.scale = self.builder.get_object('scale')
        self.scale.set_range(1.,42.)
        self.scale.set_value(42)
        self.max_filesize = 2**int(self.scale.get_value())
        self.pbar = self.builder.get_object('progressbar')
        
        self.open_diag = None
        self.finder_result = None
        self.fstree_root = FSTree()
        self.sizes = {}
        self.same_size = set()
        self.md5_todo = []
        self.md5_working = []
        self.md5_thr = None
        self.rep_files = RepFile()
        self.shown_path = ''
        self.stop = False
        self.show_all = True
        self.shown_keys = set()
        
        
        self.init_left_tree()
        self.init_right_tree()
        
        self.builder.connect_signals(self)
        self.win.show_all()
    

    def init_left_tree(self):
        ts = Gtk.TreeStore(str,GObject.TYPE_INT64,bool,bool,int)
        
        
        self.repeated_filter = ts.filter_new()
        self.repeated_filter.set_visible_func(self.repeated_visible)
        self.left_sort = Gtk.TreeModelSort(self.repeated_filter)
        self.tv_left = Gtk.TreeView(self.left_sort)
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn('Size',renderer,text = 1)
        col.set_cell_data_func(renderer,col_human,1)
        col.set_sort_column_id(1)
        self.left_sort_col = col
        self.tv_left.append_column(col)
        renderer = Gtk.CellRendererToggle()
        renderer.connect('toggled',self.on_left_toggled)
        col = Gtk.TreeViewColumn('Delete',renderer,active=2)
        self.tv_left.append_column(col)
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn('Repeated files',renderer,text=0)
        self.tv_left.append_column(col)
        self.tv_left.connect('row-activated',self.activated_repeated_tree)
        scrol  = self.builder.get_object('scrolled_left')
        scrol.add(self.tv_left)
        
        
        self.repeated_tree_store = ts
        self.left_sort_col.set_sort_order(Gtk.SortType.DESCENDING)

        self.left_sort_col.clicked()
        self.left_sort_col.clicked()

        
    def init_right_tree(self):
        store = Gtk.ListStore(str, str, int,GObject.TYPE_INT64, int,GObject.TYPE_INT64,int,int)
        
        tree = Gtk.TreeView(store)

        name_renderer = Gtk.CellRendererText()
        icon_renderer = Gtk.CellRendererPixbuf()
        name_column = Gtk.TreeViewColumn("Name")
        name_column.pack_start(icon_renderer,False)
        name_column.pack_start(name_renderer,True)
        name_column.add_attribute(icon_renderer,'icon-name',0)
        name_column.add_attribute(name_renderer,'text',1)
        tree.append_column(name_column)

        repsize_renderer = Gtk.CellRendererText()
        repsize_column = Gtk.TreeViewColumn("Rep. Size", repsize_renderer, text=5)
        repsize_column.set_cell_data_func(repsize_renderer,col_human,5)
        repsize_column.set_sort_column_id(5)
        tree.append_column(repsize_column)

        num_renderer = Gtk.CellRendererText()
        num_column = Gtk.TreeViewColumn("Number", num_renderer, text=2)
        num_column.set_sort_column_id(2)
        tree.append_column(num_column)

        rep_renderer = Gtk.CellRendererText()
        rep_column = Gtk.TreeViewColumn("Repeated", rep_renderer, text=4)
        rep_column.set_sort_column_id(4)
        tree.append_column(rep_column)

        mark_renderer = Gtk.CellRendererText()
        mark_column = Gtk.TreeViewColumn("Marked", mark_renderer, text=6)
        mark_column.set_sort_column_id(5)
        tree.append_column(mark_column)

        size_renderer = Gtk.CellRendererText()
        size_column = Gtk.TreeViewColumn("Size", size_renderer, text=3)
        size_column.set_cell_data_func(size_renderer,col_human,3)
        tree.append_column(size_column)

        tree.connect('row-activated',self.activated_fstree)
        tree.connect('button-press-event',self.right_button_press)

        scrolled = self.builder.get_object('scrolled_right')
        scrolled.add(tree)
        self.tv_right = tree
        self.selection_right = tree.get_selection()
        self.selection_right.set_mode(Gtk.SelectionMode.MULTIPLE)
        self.fs_list_store = store
        
    def repeated_visible(self,model,miter,data = None):
        """Filter to show only repeated files in currently shown tree."""
        
        if self.show_all:
            return True
        else:
            path = model.get_path(miter)
            row = model[path[0]]
            key = (row[1],row[0].encode(errors='surrogateescape'))
            return key in self.shown_keys
    
    def left_conv_to_path(self,path):
        """Retrieve path in original model after sort and filter models.""" 
        if type(path) is str:
            path = Gtk.TreePath(path)
        cpath = self.left_sort.convert_path_to_child_path(path)
        cpath = self.repeated_filter.convert_path_to_child_path(cpath)
        return cpath


    def open(self,widget,*args):
        """Open widget to select a folder to scan."""
        self.open_diag = Gtk.FileChooserDialog('Select a folder', self.win,
                Gtk.FileChooserAction.SELECT_FOLDER,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                "Select", Gtk.ResponseType.OK))
        self.open_diag.set_create_folders(False)
        resp = self.open_diag.run()
        if resp == Gtk.ResponseType.OK:
            self.scan_path()

        self.open_diag.destroy()
        
        
    def scan_path(self):
        """Instanciate and start finder class, add check_finder to timeout."""
        path = self.open_diag.get_filename()
        #TODO: Temporary solution to utf errors
        self.shown_path = path.encode()
        self.finder_thr = Finder(path)
        self.finder_thr.start()
        GObject.timeout_add(100,self.check_finder)
        self.path = path
        print('Scanning path',path)
    
    def check_finder(self):
        """Timeout function, call make_fstree when finder thread finishes."""
        if self.finder_thr.is_alive(): 
            self.pbar.pulse()
            return True
        else:
            print('Find process finished. Building file tree...')
            self.finder_result = self.finder_thr.result
            make_fstree(self.finder_result,self.fstree_root,self.sizes,self.same_size)
            print('File tree completed.')
            self.update_path()
            print('update_path completed')
            self.compute_md5list()
            print('compute_md5list returned')
            self.pbar.set_fraction(0.0)
            return False
        
        
    def compute_md5list(self):
        """Compute list of files to perform md5sum.
        
        Files with the same size are added from largest to smallest. If 
        empty files are present, they are added directly to the repeated
        files dictionary. Add a timeout function to control and check
        the progress of md5sum computation. 
        """
        for s in sorted(self.same_size,reverse=True):
            for fn in self.sizes[s]:
                if s > 0 and s < self.max_filesize:
                    self.md5_todo.append(fn)
        if 0 in self.sizes:
            self.rep_files.add_empty(self.sizes[0])
        
        GObject.timeout_add(500,self.check_md5_progress)
        #print('To compute md5 of {} files totaling {}'.format(len(self.md5_todo),human_size(sum([x.size for x in self.md5_todo]))))
        return False
    
    def check_md5_progress(self):
        """Timeout function. Check and control computation of md5sum.
        
        Create and start thread to compute md5sum. Periodically check 
        thread status recreating, starting and stoping it if necessary.
        Perform bookeeping of md5sums already computed.
        """
        if self.md5_thr is None:
            #Thread not yet started. Create one if we have work to do
            if len(self.md5_todo) > 0 and not self.stop:
                assert len(self.md5_working) == 0, 'working md5 list not empty'
                #Process larger files first
                
                self.md5_working.extend([fn for fn in self.md5_todo if fn.size <= self.max_filesize])
                self.md5_working.sort(key=lambda x:x.size,reverse=True)#This is COOL!
                sizes = np.array([fn.size for fn in self.md5_working],dtype=np.int64)
                self.progress = sizes.cumsum().astype(float)/sizes.sum()
                self.md5_todo.clear()

                self.md5_thr = threading.Thread(target= compute_md5, args = (self.md5_working,self.rep_files))
                self.md5_thr.start()
                return True #We will run again
            else:
                #Nothing to do
                return False

        elif self.md5_thr.is_alive():
            if not self.stop:
                #Thread still running. Come back later
                self.update_repeated()
                yet = len(self.md5_working)
                self.pbar.set_fraction(self.progress[-yet])
                print('Still {} files to process'.format(yet))
                return True
            else:
                #We must stop
                self.md5_todo.extend(self.md5_working)
                self.md5_working.clear()
                return True
        else:
            #Thread finished
            self.md5_thr = None
            if len(self.md5_todo) > 0 and not self.stop:
                #New stuff to do. Restart
                return True
            else:
                self.update_repeated()
                self.stop = False
                self.fstree_root.compute_aggr()
                self.update_path()
                print('Finished!')
                #We are finished!
                return False

    def update_repeated(self):
        """Append to model repeated files recently found."""
        self.rep_files.append_to_model(self.repeated_tree_store)
    
    def update_path(self):
        """Show a new path in the right pane."""
        branch = self.fstree_root.get_branch(self.shown_path)
        branch.copy_to_model(self.fs_list_store)
        if not self.show_all:
            self.shown_keys = branch.get_keys()
            self.repeated_filter.refilter()
        else:
            self.show_keys = set()
        self.path_label.set_label('Location: {}'.format(self.shown_path.decode(errors='replace')))
        

    def activated_repeated_tree(self,treeview,treepath,col):
        """Callback. Expand or collapse main row, show path in the right pane."""
        #sp = treepath.split(':')
        if  treepath.get_depth() == 1:
            #Main row
            orig_tpath = self.left_conv_to_path(treepath)
            row = self.repeated_tree_store[orig_tpath]
            if not row[3]:
                self.rep_files.add_children(self.repeated_tree_store,orig_tpath)
                treeview.expand_row(treepath,False)
            elif treeview.row_expanded(treepath):
                treeview.collapse_row(treepath)
            else:
                treeview.expand_row(treepath,False)
        else:
            treepath = self.left_conv_to_path(treepath)
            fn = self.rep_files.getfn(self.repeated_tree_store,treepath)
            fname = fn.fpath
            sp = fname.rpartition(b'/')
            self.shown_path = sp[0]
            self.update_path()
        
    
    def activated_fstree(self,widget,treepath,col):
        """Callback. Select a new folder to show."""
        titer = self.fs_list_store.get_iter(treepath)
        if self.fs_list_store[titer][0] == 'folder':
            ind = self.fs_list_store[titer][-1]
            branch = self.fstree_root.get_branch(self.shown_path)
            self.shown_path = branch.get_index(ind).path
            self.update_path()
            
    def on_left_toggled(self,widget,tpath):
        tpath = self.left_conv_to_path(tpath)
        if tpath.get_depth() == 2:
            fn  = self.rep_files.getfn(self.repeated_tree_store,tpath)
            success = self.rep_files.toggle_mark(fn)
            if success:
                self.repeated_tree_store[tpath][2] = fn.marked
                main_row = self.repeated_tree_store[tpath[0]]
                if self.rep_files.is_processed(main_row[-1]):
                    main_row[2] = True
                else:
                    main_row[2] = False
                
            
                
    def up(self,widget,*args):
        paths = self.shown_path.rpartition(b'/')
        if paths[1] != b'' and paths[2] != b'':
            self.shown_path = paths[0]
            self.update_path() 

    def on_stop(self,widget,*args):
        print('on_stop')
        self.stop = True

    def on_continue(self,widget,*args):
        print('on_continue')
        self.stop = False 
        if self.md5_thr is None:
            GObject.timeout_add(500,self.check_md5_progress)
    
    def on_show_all_button_toggled(self,widget, data = None):
        self.show_all = widget.get_active()
        self.repeated_filter.refilter()
        
    def on_action_mark_all_activate(self,action, data = None):
        model,selection = self.selection_right.get_selected_rows()
        for titer in selection:
            if self.fs_list_store[titer][0] == 'folder':
                ind = self.fs_list_store[titer][-1]
                branch = self.fstree_root.get_branch(self.shown_path).get_index(ind)
                branch.mark_all(self.rep_files)
            if self.fs_list_store[titer][0] == 'gtk-file':
                ind = self.fs_list_store[titer][-1]
                fn = self.fstree_root.get_branch(self.shown_path).get_index(ind)
                fn.mark(self.rep_files)
        branch = self.fstree_root.get_branch(self.shown_path)
        branch.compute_aggr()

        self.rep_files.update_model(self.repeated_tree_store)
        self.update_path()

        
        
    def on_action_unmark_all_activate(self,action, data = None):
        model,selection = self.selection_right.get_selected_rows()
        for titer in selection:
            if self.fs_list_store[titer][0] == 'folder':
                ind = self.fs_list_store[titer][-1]
                branch = self.fstree_root.get_branch(self.shown_path).get_index(ind)
                branch.unmark_all()
            if self.fs_list_store[titer][0] == 'gtk-file':
                ind = self.fs_list_store[titer][-1]
                fn = self.fstree_root.get_branch(self.shown_path).get_index(ind)
                fn.marked = False
        branch = self.fstree_root.get_branch(self.shown_path)
        branch.compute_aggr()

        self.rep_files.update_model(self.repeated_tree_store)
        self.update_path()

    def on_format_value(self,scale,value):
        return human_size(2**value,precision = 0)
        
    def on_scale_value_changed(self,rg):
        self.max_filesize = 2**int(self.scale.get_value())

    
    def right_button_press(self,widget,event,data=None):
        if event.button == 3:
            self.popup_menu.popup(None, None, None, None, event.button, event.time)
            return True
        else:
            return False
    
    def delete_marked(self,widget,*args):
        save_diag = Gtk.FileChooserDialog('Save as', self.win,
                    Gtk.FileChooserAction.SAVE,
                    (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                    "Save", Gtk.ResponseType.OK))
        save_diag.set_do_overwrite_confirmation(True)
        resp = save_diag.run()
        if resp == Gtk.ResponseType.OK:
            fpath = save_diag.get_filename()
            self.rep_files.to_xmlfile(fpath)
            del_out.clear()
            self.fstree_root.delete_marked()
            with open('del_out','wb') as f:
                f.write(del_out.buffer)
        save_diag.destroy()
        

    
    def back(self,widget,*args):
        pass

    def forward(self,widget,*args):
        self.rep_files.to_xmlfile('temp.xml')
        
    def on_previous(self,widget,*args):
        pass

    def on_next(self,widget,*args):
        pass

    def quit(self,widget,*args):
        diag = Gtk.Dialog( "Realy Quit?", self.win, 0,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OK, Gtk.ResponseType.OK))
        resp = diag.run()
        diag.destroy()
        if resp == Gtk.ResponseType.OK:
            Gtk.main_quit()
        else:
            return True #Keeps window from being destroyed
        



if __name__ == '__main__':
    
    GObject.threads_init()

    ui = UI()
    Gtk.main()
