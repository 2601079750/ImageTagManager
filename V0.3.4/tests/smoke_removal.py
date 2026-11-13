"""Real Tk loop: removal, restoration, folders, confirmation and retention controls."""
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from imagetag.app import App, Preview
from imagetag.core import Catalogue, file_hash
from imagetag.removal_ui import RETENTION


def main():
    with tempfile.TemporaryDirectory(prefix='shitu-removal-ui-') as temporary:
        root = Path(temporary)
        source = root / 'source'
        (source / 'nested').mkdir(parents=True)
        for name, color in (('a.png', 'coral'), ('b.png', 'teal'), ('nested/c.png', 'navy'), ('nested/d.png', 'green')):
            Image.new('RGB', (150, 100), color).save(source / name)
        c = Catalogue(root / 'data', root / 'library')
        c.set_setting('auto_sync', '0')
        c.import_paths([source], 'reference')
        tag = c.create_tag('测试角色', c.groups()[1]['id'])
        ids = [r['id'] for r in c.rows()]
        c.apply_tag(ids, tag)
        hashes = {str(p): file_hash(p) for p in source.rglob('*.png')}
        app = App(c, auto_scan=False, startup_folder=root, native_services=False)
        errors = []
        app.report_callback_exception = lambda k, e, t: errors.append(str(e))

        def pump(seconds=.15):
            app.after(round(seconds * 1000), app.quit)
            app.mainloop()

        def idle():
            deadline = time.monotonic() + 8
            while app.busy and time.monotonic() < deadline:
                pump(.06)
            assert not app.busy, 'worker timeout'
            pump(.12)
            assert not errors, errors

        try:
            pump(.6)
            app.gallery.selected = set(ids[:2])
            app.selection_changed()
            assert '2' in app.image_selection_label.cget('text')
            with patch('imagetag.removal_ui.messagebox.askyesno', return_value=False):
                app.remove_selected_images()
            assert len(c.rows()) == 4
            def confirm(*a, **kw):
                assert app._confirming_catalogue
                assert not app.run_job('nested scan', c.scan, quiet=True)
                return True
            with patch('imagetag.removal_ui.messagebox.askyesno', side_effect=confirm):
                app.remove_selected_images()
            idle()
            assert len(app.all_rows) == 2 and len(app.removed_rows) == 2
            app.set_scope('已移除')
            pump()
            assert app.gallery.selected == set()
            assert app.retention_combo.winfo_ismapped()
            assert not app.remove_images_button.winfo_ismapped()
            assert tuple(app.retention_combo.cget('values')) == tuple(RETENTION)
            app.gallery.select_all()
            assert app.gallery.selected == set(ids[:2])
            assert str(app.create_tag_button.cget('state')) == 'disabled'
            view = Preview(app, ids[0])
            pump()
            assert view.image is not None
            view.destroy()
            app.gallery.selected = {ids[0]}
            app.selection_changed()
            with patch('imagetag.removal_ui.messagebox.askyesno', return_value=True):
                app.restore_images_button.invoke()
            idle()
            assert len(app.removed_rows) == 1
            assert next(r for r in c.rows() if r['id'] == ids[0])['tags'] == {tag}
            app.gallery.select_all()
            with patch('imagetag.removal_ui.messagebox.askyesno', return_value=True):
                app.purge_records_button.invoke()
            idle()
            assert c.rows(True) == []
            c.scan()
            assert len(c.rows()) == 3
            app.set_scope('全部图片')
            pump()
            assert not app.retention_combo.winfo_ismapped()
            manager = app.sources_dialog()
            pump()
            app.set_background(source / 'a.png')
            app.theme_mode.set('自定义背景')
            app.apply_theme()
            pump(.3)
            surface = app.backdrop.glass[manager.listing]
            assert surface.canvas.winfo_ismapped()
            drawn = [surface.canvas.itemcget(i, 'text') for i in surface.canvas.find_all() if surface.canvas.type(i) == 'text']
            assert '文件夹路径' in drawn and '图库 / 已移除' in drawn, drawn
            assert any('source' in text for text in drawn), drawn
            item = next(i for i in manager.listing.get_children() if manager.listing.item(i, 'values')[0] == str(source).lower())
            manager.listing.selection_set(item)
            with patch('imagetag.removal_ui.messagebox.askyesno', return_value=True):
                manager.remove_selected()
            idle()
            assert not app.all_rows and len(app.removed_rows) == 3
            with patch('imagetag.removal_ui.messagebox.askyesnocancel', return_value=False):
                manager.restore_selected()
            idle()
            assert len(app.all_rows) == 3 and not app.removed_rows
            assert all(r['tags'] == {tag} for r in c.rows())
            manager.destroy()
            app.set_scope('已移除')
            # Every preset persists, and wheel input cannot accidentally change it.
            for choice in ('3 天', '7 天', '15 天', '30 天', '不自动删除'):
                app.retention_choice.set(choice)
                with patch('imagetag.removal_ui.messagebox.askyesno', return_value=True):
                    app.retention_combo.event_generate('<<ComboboxSelected>>')
                idle()
                assert c.setting('removed_retention_days') == RETENTION[choice]
                app.retention_combo.event_generate('<MouseWheel>', delta=-120)
                assert app.retention_choice.get() == choice
            c.remove_images([ids[0]])
            with c.connection() as db:
                db.execute('UPDATE images SET removed_at=? WHERE id=?', (time.time()-31*86400, ids[0]))
            app.reload()
            app.retention_choice.set('3 天')
            with patch('imagetag.removal_ui.messagebox.askyesno', return_value=False):
                app.retention_changed()
            assert c.setting('removed_retention_days') == '0' and len(c.rows(True)) == 1
            with patch('imagetag.removal_ui.messagebox.askyesno', return_value=True):
                app.retention_choice.set('3 天')
                app.retention_changed()
            idle()
            assert not c.rows(True)
            c.scan()
            assert len(c.rows()) == 2
            app.reload()
            # Scheduled cleanup also operates when automatic image sync is off.
            remaining = c.rows()[0]['id']
            c.remove_images([remaining])
            with c.connection() as db:
                db.execute('UPDATE images SET removed_at=? WHERE id=?', (time.time()-4*86400, remaining))
            app.removal_maintenance()
            idle()
            assert c.rows(True) == [] and len(c.rows()) == 1
            app.set_background(source / 'a.png')
            for theme in ('浅色', '深色', '自定义背景'):
                app.theme_mode.set(theme)
                app.apply_theme()
                for scope in ('已移除', '全部图片'):
                    app.set_scope(scope)
                    pump(.3)
                    assert app.result_label.winfo_ismapped()
                    for widget in (app.retention_combo,) if scope == '已移除' else (app.remove_images_button,):
                        assert widget.winfo_ismapped()
                        assert widget.winfo_rootx()+widget.winfo_width() <= app.winfo_rootx()+app.winfo_width()
            assert all(file_hash(Path(p)) == h for p,h in hashes.items())
            assert not errors, errors
        finally:
            if app.winfo_exists():
                idle()
                app.exit_app()
            app.gallery.pool.shutdown(wait=True)
            app.gallery.anim_pool.shutdown(wait=True)
            app.worker.shutdown(wait=True)
        print('Removal UI passed: cancel/confirm, stable batch scope, restore tags, purge, folder restore, all retention periods, wheel guard, three themes and original-file hashes.')


if __name__ == '__main__':
    main()
