"""Image removal and folder management actions, using the existing application style."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .removal import within

RETENTION = {'不自动删除': '0', '3 天': '3', '7 天': '7', '15 天': '15', '30 天': '30'}


class RemovalUI:
    def confirm_catalogue(self, method, title, text, parent=None):
        # A native modal dialog runs a nested Tk loop. Do not start a scan there.
        self._confirming_catalogue = True
        try:
            return method(title, text, parent=parent or self)
        finally:
            self._confirming_catalogue = False

    def remove_selected_images(self):
        if self.scope == '已移除' or not self.editable() or not self.ensure_selected():
            return
        ids = tuple(r['id'] for r in self.selected_rows())
        if self.confirm_catalogue(messagebox.askyesno, '移除图片', f'从拾图中移除这 {len(ids)} 张图片？\n\n磁盘中的原图片会保留，可在“已移除”中恢复。'):
            self.run_job('移除图片', lambda _: self.catalogue.remove_images(ids))

    def restore_selected_images(self):
        if self.scope != '已移除' or not self.editable() or not self.ensure_selected():
            return
        ids = tuple(r['id'] for r in self.selected_rows())
        if self.confirm_catalogue(messagebox.askyesno, '恢复图片', f'恢复这 {len(ids)} 张图片及其原有标签？\n\n其他图片的移除状态和文件夹同步状态保持原样。\n原图缺失的记录会进入“原图缺失”，可重新关联。'):
            self.run_job('恢复图片', lambda _: self.catalogue.restore_images(ids))

    def delete_removed_records(self):
        if self.scope != '已移除' or not self.editable() or not self.ensure_selected():
            return
        ids = tuple(r['id'] for r in self.selected_rows())
        if self.confirm_catalogue(messagebox.askyesno, '删除移除记录', f'彻底删除所选的 {len(ids)} 条移除记录及其图片标签关联？\n\n删除后无法从“已移除”恢复；磁盘原图和全局标签保留。\n扫描排除规则会保留，自动同步不会重新导入这些文件。\n以后可主动重新导入，但已清除的标签关联不会恢复。'):
            self.run_job('删除移除记录', lambda _: self.catalogue.purge_removed(ids))

    def retention_changed(self, _=None):
        if not self.editable():
            self.refresh_retention()
            return
        value = RETENTION[self.retention_choice.get()]
        expired = self.catalogue.expired_removed_ids()
        if value != '0':
            import time
            cutoff = time.time() - int(value) * 86400
            expired = [r['id'] for r in self.removed_rows if r['removed_at'] <= cutoff]
            text = f'按移除时间计算，满 {value} 天后自动删除记录和图片标签关联。\n原图、全局标签及扫描排除规则保留。'
            if expired:
                text += f'\n\n现有 {len(expired)} 条记录已到期，启用后将立即清理。'
            if not self.confirm_catalogue(messagebox.askyesno, '自动删除移除记录', text + '\n\n启用此设置？'):
                self.refresh_retention()
                return
        self.catalogue.set_setting('removed_retention_days', value)
        self.refresh_retention()
        self.run_job('清理到期移除记录', lambda _: self.catalogue.purge_expired(), quiet=True)

    def refresh_retention(self):
        value = self.catalogue.setting('removed_retention_days', '0')
        self.retention_choice.set(next((k for k, v in RETENTION.items() if v == value), '不自动删除'))

    def removal_maintenance(self):
        if self.closing:
            return
        if not self.busy and not getattr(self, '_confirming_catalogue', False) and self.catalogue.expired_removed_ids():
            self.run_job('自动清理移除记录', lambda _: self.catalogue.purge_expired(), quiet=True)
        self.after(60000, self.removal_maintenance)

    def image_context_menu(self, event):
        image_id = self.gallery.at(event)
        if image_id is None:
            return
        previous = getattr(self, '_image_menu', None)
        if previous is not None:
            previous.destroy()
        self.gallery.focus_set()
        if image_id not in self.gallery.selected:
            self.gallery.selected = {image_id}
            self.gallery.anchor = image_id
            self.gallery.request_redraw()
            self.selection_changed()
        menu = tk.Menu(self, tearoff=False, bg=self.palette['PANEL'], fg=self.palette['INK'],
                       activebackground=self.palette['SELECT'], activeforeground=self.palette['ACCENT_INK'])
        self._image_menu = menu
        count = len(self.gallery.selected)
        if self.scope == '已移除':
            menu.add_command(label=f'恢复所选的 {count} 张图片…', command=self.restore_selected_images)
            menu.add_command(label=f'删除所选的 {count} 条记录…', command=self.delete_removed_records)
        else:
            menu.add_command(label='移除图片…' if count == 1 else f'移除所选的 {count} 张图片…', command=self.remove_selected_images)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def folder_manager(self):
        from . import app as ui
        previous = getattr(self, '_folder_window', None)
        if previous and previous.winfo_exists():
            previous.lift()
            return previous
        dialog = self._folder_window = ui.Popup(self, '文件夹与路径管理', '920x690')
        ui.label(dialog, '文件夹与路径管理', size=17, bold=True).pack(anchor='w', padx=22, pady=(20, 8))
        ui.label(dialog, '停止同步会保留图库中的图片；移除会包含子文件夹，磁盘原图始终保留。', color=ui.MUTED).pack(anchor='w', padx=22)
        area = tk.Frame(dialog, bg=ui.PANEL)
        area.pack(fill='both', expand=True, padx=22, pady=14)
        listing = dialog.listing = ttk.Treeview(area, columns=('path', 'state', 'count'), show='headings', selectmode='browse')
        listing._glass_surface = True
        for name, title, width in (('path', '文件夹路径', 570), ('state', '状态', 135), ('count', '图库 / 已移除', 110)):
            listing.heading(name, text=title)
            listing.column(name, width=width, minwidth=80, stretch=name == 'path')
        listing.grid(row=0, column=0, sticky='nsew')
        ttk.Scrollbar(area, command=listing.yview).grid(row=0, column=1, sticky='ns')
        vertical = area.grid_slaves(row=0, column=1)[0]
        listing.configure(yscrollcommand=vertical.set)
        horizontal = ttk.Scrollbar(area, orient='horizontal', command=listing.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        listing.configure(xscrollcommand=horizontal.set)
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        entries = {}

        def refresh():
            selected = listing.selection()
            old_path = entries[selected[0]]['path'] if selected and selected[0] in entries else None
            entries.clear()
            listing.delete(*listing.get_children())
            sources = self.catalogue.sources()
            paths = {s['path']: dict(s) for s in sources}
            for r in self.catalogue.scan_rules():
                if r['kind'] == 'directory' and r['excluded']:
                    paths.setdefault(r['path'], {'path': r['path'], 'enabled': 0, 'kind': 'excluded'})
            rules = self.catalogue.scan_rules()
            active, removed = self.catalogue.rows(), self.catalogue.rows(removed=True)
            for index, entry in enumerate(paths.values()):
                iid = str(index)
                entries[iid] = entry
                excluded = self.catalogue.excluded_path(entry['path'], rules)
                state = '已移除范围' if excluded else ('同步中' if entry['enabled'] else '已停止同步')
                prefix = '[图片库] ' if entry['kind'] == 'library' else ''
                count = f"{sum(within(r['path'],entry['path']) for r in active)} / {sum(within(r['path'],entry['path']) for r in removed)}"
                listing.insert('', 'end', iid=iid, values=(prefix + entry['path'], state, count))
                if entry['path'] == old_path:
                    listing.selection_set(iid)
            if not listing.selection() and entries:
                listing.selection_set(next(iter(entries)))

        def selected():
            choice = listing.selection()
            return entries.get(choice[0]) if choice else None

        def remove(root=None):
            if not self.editable():
                return
            entry = selected()
            root = root or (entry['path'] if entry else None)
            if not root:
                return
            count = len(self.catalogue.folder_images(root))
            text = f'移除以下目录及全部子目录内的 {count} 张图片？\n\n{root}\n\n磁盘原图保留。该范围将停止自动导入新图片。\n即使另有父目录或子目录来源，这个排除范围也会生效。'
            if self.confirm_catalogue(messagebox.askyesno, '移除文件夹内图片', text, dialog):
                self.run_job('移除文件夹内图片', lambda _: self.catalogue.remove_folder(root))

        def choose_remove():
            root = filedialog.askdirectory(parent=dialog, title='选择要从拾图中移除的文件夹（包含子文件夹）')
            if root:
                remove(root)

        def toggle():
            if not self.editable():
                return
            entry = selected()
            if not entry or 'id' not in entry:
                return
            if self.catalogue.excluded_path(entry['path'], self.catalogue.scan_rules()):
                restore()
                return
            enabled = not entry['enabled']
            text = ('恢复扫描此来源？' if enabled else '停止扫描此来源？已经导入的图片与标签继续保留。')
            text += f"\n\n{entry['path']}\n\n如果同时存在启用的父目录或子目录来源，重叠范围仍会扫描。"
            if self.confirm_catalogue(messagebox.askyesno, '恢复同步' if enabled else '停止同步', text, dialog):
                self.run_job('更新来源同步状态', lambda _: self.catalogue.set_source_enabled(entry['id'], enabled))

        def restore():
            if not self.editable():
                return
            entry = selected()
            if not entry:
                return
            root = entry['path']
            count = len(self.catalogue.folder_images(root, removed=True))
            text = f'恢复此目录及子目录内的 {count} 条图片记录和原有标签：\n\n{root}\n\n是否同时恢复此范围的自动同步？\n“是”：恢复记录并允许导入新图片。\n“否”：仅恢复现有记录，继续排除新图片。\n已经删除的记录及标签关联无法恢复。'
            answer = self.confirm_catalogue(messagebox.askyesnocancel, '恢复文件夹', text, dialog)
            if answer is not None:
                self.run_job('恢复文件夹', lambda _: self.catalogue.restore_folder(root, resume_sync=answer))

        def recover():
            if self.editable():
                root = filedialog.askdirectory(parent=dialog, title='选择可能包含丢失图片的文件夹')
                if root:
                    self.run_job('查找丢失图片', lambda progress: self.catalogue.recover([Path(root)], progress))

        def relocate():
            if not self.editable():
                return
            entry = selected()
            if entry and 'id' in entry:
                root = filedialog.askdirectory(parent=dialog, title='选择该文件夹的新位置')
                if root:
                    self.run_job('重新定位文件夹', lambda progress: self.catalogue.relocate_source(entry['id'], Path(root), progress))

        actions = tk.Frame(dialog, bg=ui.PANEL)
        actions.pack(fill='x', padx=22, pady=5)
        for text, action in (('停止 / 恢复同步…', toggle), ('移除所选文件夹内图片…', remove), ('恢复所选文件夹…', restore)):
            ui.button(actions, text, action, padx=9).pack(side='left', padx=(0, 6))
        secondary = tk.Frame(dialog, bg=ui.PANEL)
        secondary.pack(fill='x', padx=22, pady=5)
        for text, action in (('选择其他子文件夹移除…', choose_remove), ('重新定位所选文件夹…', relocate), ('查找丢失图片…', recover)):
            ui.button(secondary, text, action, padx=9).pack(side='left', padx=(0, 6))
        ui.label(dialog, '恢复图片会保留现有标签；删除移除记录后，只能重新导入原图。\n图片库路径保持配置；此处的移除操作不会删除磁盘文件或文件夹。', color=ui.MUTED, size=9, justify='left').pack(anchor='w', padx=22, pady=12)
        import os
        ui.button(dialog, '打开图片库', lambda: os.startfile(self.catalogue.library_dir)).pack(anchor='w', padx=22, pady=(0, 16))
        dialog.refresh = refresh
        dialog.remove_selected = remove
        dialog.restore_selected = restore
        dialog.toggle_source = toggle
        refresh()
        return dialog
