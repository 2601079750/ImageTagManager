"""Check draft color previews and explicit commit through a real Tk loop."""
import logging
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from imagetag.app import App
from imagetag.core import Catalogue


def main():
    with tempfile.TemporaryDirectory(prefix='imagetag-color-draft-') as temporary:
        root = Path(temporary)
        cat = Catalogue(root / 'data', root / 'library')
        app = App(cat, auto_scan=False, startup_folder=root, native_services=False)
        errors = []
        app.report_callback_exception = lambda kind, value, trace: errors.append(str(value))

        def pump(seconds=.35):
            timer = app.after(round(seconds * 1000), app.quit)
            try:
                app.mainloop()
            finally:
                app.after_cancel(timer)

        def close_window(dialog):
            # Invoke the same registered handler as the title-bar X button.
            dialog.tk.call(dialog.protocol('WM_DELETE_WINDOW'))
            pump()

        def click(button):
            pump(.12)
            surface = app.backdrop.glass[button]
            x, y = button.winfo_width() // 2, button.winfo_height() // 2
            for event in ('<Enter>', '<ButtonPress-1>', '<ButtonRelease-1>'):
                surface.canvas.event_generate(event, x=x, y=y)
                pump(.04)

        try:
            background = root / 'background.png'
            Image.new('RGB', (320, 240), '#8096a0').save(background)
            app.set_background(background)
            settings = app.settings_dialog()
            pump(.5)
            for mode in ('浅色', '深色', '自定义背景'):
                app.theme_mode.set(mode)
                settings.change_theme()
                # Opening the dialog must keep an earlier pending choice.
                original = '#127c98'
                settings.choose_accent(original)
                dialog = settings.custom_color()
                assert cat.setting('custom_accent') == original
                assert settings.custom_color() is dialog
                assert app.grab_current() is dialog
                pump()
                with patch('imagetag.features.colorchooser.askcolor', return_value=((255, 0, 255), '#ff00ff')):
                    dialog.chooser_button.invoke()
                assert app.custom_accent.get() == '#ff00ff'
                assert app.palette['ACCENT'] == '#ff00ff'
                assert app.create_tag_button.cget('bg') == '#ff00ff'
                assert settings.custom_swatch.selected
                # Wait past the old autosave interval, then exercise a flush
                # caused by an independent appearance setting as well.
                pump(.6)
                assert cat.setting('custom_accent') == original
                app.schedule_appearance_save()
                pump()
                app.persist_opacity()
                assert cat.setting('custom_accent') == original
                with patch('imagetag.features.colorchooser.askcolor', return_value=(None, None)):
                    dialog.chooser_button.invoke()
                assert app.custom_accent.get() == '#ff00ff'
                close_window(dialog)
                assert app.custom_accent.get() == original
                assert app.palette['ACCENT'] == original
                assert app.create_tag_button.cget('bg') == original
                assert cat.setting('custom_accent') == original
                assert app.grab_current() is None

                dialog = settings.custom_color()
                dialog.color_value.set('#2030FF')
                assert app.custom_accent.get() == '#2030ff'
                with patch.object(app, 'screen_pick', side_effect=lambda owner, accept: accept('#00ffaa')):
                    dialog.pick_button.invoke()
                assert app.custom_accent.get() == '#00ffaa'
                assert cat.setting('custom_accent') == original
                # Exercise the real eyedropper cancellation/grab restoration
                # with a generated frame, without capturing desktop contents.
                with patch('imagetag.features.ImageGrab.grab', return_value=Image.new('RGB', (320, 200), '#334455')):
                    dialog.pick_button.invoke()
                overlay = app.grab_current()
                assert overlay is not dialog
                pump(.1)
                overlay.event_generate('<Escape>')
                pump(.1)
                assert app.grab_current() is dialog
                assert app.custom_accent.get() == '#00ffaa'
                # Invalid/partial input neither commits nor closes the dialog.
                dialog.color_value.set('#12')
                with patch('imagetag.features.messagebox.showinfo') as warning:
                    dialog.apply_button.invoke()
                assert warning.called and dialog.winfo_exists()
                assert app.custom_accent.get() == '#00ffaa'
                assert cat.setting('custom_accent') == original
                dialog.color_value.set('#128C98')
                click(dialog.apply_button)
                assert not dialog.winfo_exists()
                assert app.custom_accent.get() == '#128c98'
                assert cat.setting('custom_accent') == '#128c98'
                assert Catalogue(cat.data_dir, cat.library_dir).setting('custom_accent') == '#128c98'
                pump()
                assert app.custom_accent.get() == '#128c98'

                # Escape cancels the entire draft, including a valid preview
                # followed by an incomplete input value.
                dialog = settings.custom_color()
                dialog.color_value.set('#a34683')
                dialog.color_value.set('invalid')
                dialog.focus_force()
                pump(.1)
                dialog.event_generate('<Escape>')
                pump()
                assert not dialog.winfo_exists()
                assert app.custom_accent.get() == '#128c98'
                assert cat.setting('custom_accent') == '#128c98'

            # Closing the parent settings must discard its open color draft.
            dialog = settings.custom_color()
            dialog.color_value.set('#2030ff')
            settings.destroy()
            pump()
            assert not dialog.winfo_exists()
            assert app.custom_accent.get() == '#128c98'
            assert cat.setting('custom_accent') == '#128c98'
            settings = app.settings_dialog()
            dialog = settings.custom_color()
            dialog.color_value.set('#ff0066')
            app.schedule_appearance_save()
            app.exit_app()
            assert cat.setting('custom_accent') == '#128c98'
            assert not errors, errors
        finally:
            if not app.closing:
                app.exit_app()
            for pool in (app.gallery.pool, app.gallery.anim_pool, app.worker, app.network_pool):
                pool.shutdown(wait=True)
            logging.shutdown()
        print('Color dialog passed: three-theme immediate preview, chooser/picker/input, explicit commit, X/Escape/parent/exit cancellation and autosave isolation.')


if __name__ == '__main__':
    main()
