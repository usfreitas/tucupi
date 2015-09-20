#!/usr/bin/env python3
import threading

from gi.repository import Gtk,GObject,GLib

import time
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


def human_size(s):
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
        return '{0:.2f}{1}B'.format(s/(1024**pre_val),bin_prefix[pre_val])
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
            key = (self.size,self.md5)
            rep_file.toggle_mark(key,self)


class RepFile(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.size_md5 = {}
        self.repeated = set()
        
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
            main_iter = ts.get_iter_first()
            while main_iter != None:
                main_row = ts[main_iter]
                key = (main_row[1], main_row[0].encode(errors='surrogateescape'))
                files = self.size_md5[key]
                nchildren = ts.iter_n_children(main_iter)
                assert len(files) == nchildren, 'different number of files in treestore'
                for k in range(nchildren):
                    child = ts[ts.iter_nth_child(main_iter,k)]
                    fpath = child[0]
                    fn = files[k]
                    assert fn.fpath.decode(errors='surrogateescape') == fpath, 'files out of order in treestore'
                    child[2] = fn.marked
                main_iter = ts.iter_next(main_iter)
            
    
    def append_to_model(self,ts):
        keys_copied = set()
        with self.lock:
            main_iter = ts.get_iter_first()
            while main_iter != None:
                main_row = ts[main_iter]
                key = (main_row[1], main_row[0].encode(errors='surrogateescape'))
                files = self.size_md5[key]
                nchildren = ts.iter_n_children(main_iter)
                for k in range(len(files)-nchildren):
                    f = files[nchildren+k]
                    ts.append(main_iter,[f.fpath.decode(errors='surrogateescape'), files[0].size, f.marked])
                
                keys_copied.add(key)
                main_iter = ts.iter_next(main_iter)
            
            for k in self.repeated:
                if k not in keys_copied:
                    files = self.size_md5[k]
                    main_row = ts.append(None,[files[0].md5.decode(errors='surrogateescape'), files[0].size ,False])
                    for f in files:
                        ts.append(main_row,[f.fpath.decode(errors='surrogateescape'), files[0].size, f.marked])
    
    def getfn(self,key,fpath):
        with self.lock:
            for fn in self.size_md5[key]:
                if fn.fpath == fpath:
                    return fn
        raise ValueError('file node not found ({})'.format(fpath))
    
    def toggle_mark(self,key,fn):
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
                        md5.value = key[1].decode(errors='surrogateescape')
                        f.setAttributeNode(md5)
                        f.setAttributeNode(size)
                        for fn in fn_list:
                            if fn.marked:
                                ff = xmldoc.createElement('deleted')
                            else:
                                ff = xmldoc.createElement('kept')
                            fpath = xmldoc.createTextNode(fn.fpath.decode(errors='surrogateescape'))
                            ff.appendChild(fpath)
                            f.appendChild(ff)
                        root.appendChild(f)
            f = open(fname,'wt')
            f.write(xmldoc.toprettyxml(indent="    "))
        
                        




class FSTree(object):
    def __init__(self):
        self.branches = {}
        self.leaves = {}
        self.aggr_attrib = np.zeros((5,),dtype = np.int64)
        
    def add_leaf(self,leaf_path,leaf_attib):
        p = leaf_path.partition('/')
        if p[1] == '': 
            #Leaf
            if p[0] not in self.leaves:
                self.leaves[p[0]] = leaf_attib
                return True
            else:
                return False
        else:
            assert len(p[2]) >0, 'Empty leaf inserted'
            if p[0] not in self.branches:
                self.branches[p[0]] = FSTree()
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
        p = branch_path.partition('/')
        if p[1] == '' or p[2] == '': 
            return self.branches[p[0]]
            
        else:
            return self.branches[p[0]].get_branch(p[2])

    def get_leaf(self,leaf_path):
        p = leaf_path.partition('/')
        if p[1] == '': 
            #Leaf
            return self.leaves[p[0]]
        else:
            assert len(p[2]) >0, 'Trying to get an empty leaf'
            return self.branches[p[0]].get_leaf(p[2])

    
    def copy_to_model(self,list_store):
        ncol = list_store.get_n_columns
        list_store.clear()
        for br_name,br in self.branches.items():
            row = ['folder', br_name]
            row.extend(br.aggr_attrib.tolist())
            list_store.append(row)
        for lf_name,att in self.leaves.items():
            row = ['gtk-file',lf_name]
            row.extend([ 1, att.size ,int(att.repeated),int(att.repeated)*att.size,int(att.marked)])
            list_store.append(row)
    
    def get_keys(self,keys = None):
        if keys is None:
            keys = set()

        for br in self.branches.values():
            br.get_keys(keys)
        for fn in self.leaves.values():
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
        if tree_root.add_leaf(resp[2].decode(errors='surrogateescape'),file_node):
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
        self.popup_menu = self.builder.get_object('popup_menu')
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
        ts = Gtk.TreeStore(str,GObject.TYPE_INT64,bool)
        
        
        self.repeated_filter = ts.filter_new()
        self.repeated_filter.set_visible_func(self.repeated_visible)
        self.left_sort = Gtk.TreeModelSort(self.repeated_filter)
        self.tv_left = Gtk.TreeView(self.left_sort)
        renderer = Gtk.CellRendererToggle()
        renderer.connect('toggled',self.on_left_toggled)
        col = Gtk.TreeViewColumn('Delete',renderer,active=2)
        self.tv_left.append_column(col)
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn('Repeated files',renderer,text=0)
        self.tv_left.append_column(col)
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn('Size',renderer,text = 1)
        col.set_cell_data_func(renderer,col_human,1)
        col.set_sort_column_id(1)
        self.left_sort_col = col
        self.tv_left.append_column(col)
        self.tv_left.connect('row-activated',self.activated_repeated_tree)
        scrol  = self.builder.get_object('scrolled_left')
        scrol.add(self.tv_left)
        
        
        self.repeated_tree_store = ts
        self.left_sort_col.set_sort_order(Gtk.SortType.DESCENDING)

        self.left_sort_col.clicked()
        self.left_sort_col.clicked()

        
    def init_right_tree(self):
        store = Gtk.ListStore(str, str, int,GObject.TYPE_INT64, int,GObject.TYPE_INT64,int)
        
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
        if self.show_all:
            return True
        else:
            path = model.get_path(miter)
            row = model[path[0]]
            key = (row[1],row[0].encode(errors='surrogateescape'))
            return key in self.shown_keys
    
    def left_conv_to_path(self,path):
        if type(path) is str:
            path = Gtk.TreePath(path)
        cpath = self.left_sort.convert_path_to_child_path(path)
        cpath = self.repeated_filter.convert_path_to_child_path(cpath)
        return cpath


    def open(self,widget,*args):
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
        path = self.open_diag.get_filename()
        self.shown_path = path
        self.finder_thr = Finder(path)
        self.finder_thr.start()
        GObject.timeout_add(100,self.check_finder)
        self.path = path
    
    def check_finder(self):
        if self.finder_thr.is_alive(): 
            return True
        else:
            self.finder_result = self.finder_thr.result
            make_fstree(self.finder_result,self.fstree_root,self.sizes,self.same_size)
            self.update_path()
            self.compute_md5list()
            return False
        
        
    def compute_md5list(self):
        for s in sorted(self.same_size,reverse=True):
            for fn in self.sizes[s]:
                if s > 0 and fn not in self.md5_todo:
                    self.md5_todo.append(fn)
        if 0 in self.sizes:
            self.rep_files.add_empty(self.sizes[0])
        
        GObject.timeout_add(500,self.check_md5_progress)
        #print('To compute md5 of {} files totaling {}'.format(len(self.md5_todo),human_size(sum([x.size for x in self.md5_todo]))))
        return False
    
    def check_md5_progress(self):
        if self.md5_thr is None:
            #Thread not yet started. Create one if work to do
            if len(self.md5_todo) > 0 and not self.stop:
                assert len(self.md5_working) == 0, 'working md5 list not empty'
                #Process larger files first
                self.md5_todo.sort(key=lambda x:x.size,reverse=True)#This is COOL!
                self.md5_working.extend(self.md5_todo)
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
                print('Still {} files to process'.format(len(self.md5_working)))
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
        self.rep_files.append_to_model(self.repeated_tree_store)
    
    def update_path(self):
        branch = self.fstree_root.get_branch(self.shown_path)
        branch.copy_to_model(self.fs_list_store)
        self.shown_keys = branch.get_keys()
        self.repeated_filter.refilter()
        self.path_label.set_label('Location: {}'.format(self.shown_path))
        

    def activated_repeated_tree(self,treeview,treepath,col):
        #sp = treepath.split(':')
        if  treepath.get_depth() == 1:
            #Main row
            if treeview.row_expanded(treepath):
                treeview.collapse_row(treepath)
            else:
                treeview.expand_row(treepath,False)
        else:
            treepath = self.left_conv_to_path(treepath)
            fname = self.repeated_tree_store[treepath][0]
            sp = fname.rpartition('/')
            self.shown_path = sp[0]
            self.update_path()
        
    
    def activated_fstree(self,widget,treepath,col):
        titer = self.fs_list_store.get_iter(treepath)
        if self.fs_list_store[titer][0] == 'folder':
            self.shown_path = self.shown_path + '/' +self.fs_list_store[titer][1]
            self.update_path()
            
    def on_left_toggled(self,widget,tpath):
        tpath = self.left_conv_to_path(tpath)
        if tpath.get_depth() == 2:
            main_row = self.repeated_tree_store[tpath[0]]
            key = (main_row[1],main_row[0].encode(errors='surrogateescape'))
            fn  = self.rep_files.getfn(key,self.repeated_tree_store[tpath][0].encode(errors='surrogateescape'))
            success = self.rep_files.toggle_mark(key,fn)
            if success:
                self.repeated_tree_store[tpath][2] = fn.marked
            
                
    def up(self,widget,*args):
        paths = self.shown_path.rpartition('/')
        if paths[1] != '' and paths[2] != '':
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
                branch = self.fstree_root.get_branch(self.shown_path+'/'+self.fs_list_store[titer][1])
                branch.mark_all(self.rep_files)
            if self.fs_list_store[titer][0] == 'gtk-file':
                fpath = self.shown_path+'/'+self.fs_list_store[titer][1]
                fn = self.fstree_root.get_leaf(fpath)
                fn.mark(self.rep_files)
        branch = self.fstree_root.get_branch(self.shown_path)
        branch.compute_aggr()

        self.rep_files.update_model(self.repeated_tree_store)
        self.update_path()

        
        
    def on_action_unmark_all_activate(self,action, data = None):
        model,selection = self.selection_right.get_selected_rows()
        for titer in selection:
            if self.fs_list_store[titer][0] == 'folder':
                branch = self.fstree_root.get_branch(self.shown_path+'/'+self.fs_list_store[titer][1])
                branch.unmark_all()
            if self.fs_list_store[titer][0] == 'gtk-file':
                fpath = self.shown_path+'/'+self.fs_list_store[titer][1]
                fn = self.fstree_root.get_leaf(fpath)
                fn.marked = False
        branch = self.fstree_root.get_branch(self.shown_path)
        branch.compute_aggr()

        self.rep_files.update_model(self.repeated_tree_store)
        self.update_path()
    
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
