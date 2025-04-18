import gi
import subprocess
import threading
from queue import Queue
from datetime import datetime

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

APP_ID = "org.example.DistroboxManager"

class CreateProgressDialog(Adw.Window):
    def __init__(self, parent, task_queue):
        super().__init__(
            transient_for=parent,
            modal=True,
            default_width=600,
            default_height=500,
            title="Создание контейнера",
            deletable=False
        )
        self.task_queue = task_queue
        
        main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12
        )
        self.set_content(main_box)
        
        # Прогресс-бар
        self.progressbar = Gtk.ProgressBar(show_text=True)
        main_box.append(self.progressbar)
        
        # Статус
        self.status_label = Gtk.Label(
            wrap=True, 
            xalign=0,
            css_classes=["caption"]
        )
        main_box.append(self.status_label)
        
        # Консольный вывод
        self.console_output = Gtk.TextView(
            editable=False,
            monospace=True,
            cursor_visible=False,
            margin_top=12
        )
        self.console_buffer = self.console_output.get_buffer()
        scrolled = Gtk.ScrolledWindow(
            hexpand=True,
            vexpand=True,
            child=self.console_output
        )
        main_box.append(scrolled)
        
        # Кнопка отмены
        self.cancel_btn = Gtk.Button(
            label="Отмена",
            css_classes=["destructive-action"],
            margin_top=12
        )
        main_box.append(self.cancel_btn)
        
        GLib.timeout_add(100, self.update_progress)

    def update_progress(self):
        while not self.task_queue.empty():
            item = self.task_queue.get()
            
            if isinstance(item, tuple):
                # Обработка прогресса
                progress, status, done = item
                self.progressbar.set_fraction(progress)
                self.progressbar.set_text(f"{int(progress*100)}%")
                self.status_label.set_label(status)
                
                if done:
                    if progress == 1.0:
                        self.status_label.set_label("Контейнер успешно создан!")
                        GLib.timeout_add(2000, self.destroy)
                    else:
                        self.status_label.set_label(f"Ошибка: {status}")
                        self.cancel_btn.set_label("Закрыть")
                    return False
            elif isinstance(item, str):
                # Добавление вывода в консоль
                timestamp = datetime.now().strftime("[%H:%M:%S] ")
                end_iter = self.console_buffer.get_end_iter()
                self.console_buffer.insert(end_iter, timestamp + item)
                self.console_output.scroll_to_iter(end_iter, 0, False, 0, 0)
        
        return True

class DistroboxManager(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("Distrobox Manager")
        self.set_default_size(800, 600)
        self.task_queue = Queue()
        
        # Main container
        main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0
        )
        self.set_content(main_box)
        
        # HeaderBar
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Distrobox Manager", subtitle="Управление контейнерами"))
        
        self.refresh_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Обновить список"
        )
        self.create_btn = Gtk.Button(
            icon_name="list-add-symbolic",
            css_classes=["suggested-action"],
            tooltip_text="Новый контейнер"
        )
        
        header.pack_start(self.refresh_btn)
        header.pack_end(self.create_btn)
        main_box.append(header)
        
        # Container list
        self.container_list = Gtk.ListBox(
            css_classes=["boxed-list"],
            selection_mode=Gtk.SelectionMode.NONE
        )
        scrolled = Gtk.ScrolledWindow(
            hexpand=True,
            vexpand=True
        )
        scrolled.set_child(self.container_list)
        main_box.append(scrolled)
        
        # Connect signals
        self.refresh_btn.connect("clicked", self.refresh_containers)
        self.create_btn.connect("clicked", self.show_create_dialog)
        self.refresh_containers()
    
    def refresh_containers(self, *_):
        for child in self.container_list:
            self.container_list.remove(child)
        
        try:
            result = subprocess.run(
                ["distrobox", "list"],
                capture_output=True,
                text=True,
                check=True
            )
            lines = result.stdout.strip().splitlines()[1:]
            
            for line in lines:
                fields = [field.strip() for field in line.split("|")]
                if len(fields) >= 4:
                    name, status, image, created = fields[:4]
                    row = self.create_container_row(name, status, image, created)
                    self.container_list.append(row)
        
        except subprocess.CalledProcessError as e:
            self.show_error(f"Ошибка получения списка: {e.stderr}")
    
    def create_container_row(self, name, status, image, created):
        row = Adw.ActionRow(
            title=name,
            subtitle=f"{image} — {created}",
            activatable=False
        )
        
        status_icon = Gtk.Image(
            icon_name="emblem-default-symbolic" if "running" in status else "emblem-important-symbolic",
            tooltip_text=status
        )
        status_icon.add_css_class("dim-label")
        row.add_prefix(status_icon)
        
        btn_box = Gtk.Box(spacing=6)
        
        launch_btn = Gtk.Button(
            icon_name="utilities-terminal-symbolic",
            css_classes=["flat"],
            tooltip_text="Запустить терминал"
        )
        launch_btn.connect("clicked", lambda *_: self.launch_container(name))
        
        delete_btn = Gtk.Button(
            icon_name="user-trash-symbolic",
            css_classes=["flat", "destructive-action"],
            tooltip_text="Удалить"
        )
        delete_btn.connect("clicked", lambda *_: self.delete_container(name))
        
        btn_box.append(launch_btn)
        btn_box.append(delete_btn)
        row.add_suffix(btn_box)
        
        return row
    
    def launch_container(self, name):
        try:
            subprocess.Popen(["ptyxis", "--", "distrobox", "enter", name])
        except Exception as e:
            self.show_error(f"Ошибка запуска: {str(e)}")
    
    def delete_container(self, name):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=f"Удалить {name}?",
            body="Все данные в контейнере будут безвозвратно удалены.",
            close_response="cancel"
        )
        dialog.add_response("cancel", "Отмена")
        dialog.add_response("delete", "Удалить")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response::delete", lambda *_: self.confirm_delete(name))
        dialog.present()
    
    def confirm_delete(self, name):
        try:
            subprocess.run(
                ["distrobox", "rm", "--force", name],
                check=True
            )
            self.refresh_containers()
        except subprocess.CalledProcessError as e:
            self.show_error(f"Ошибка удаления: {e.stderr}")
    
    def show_create_dialog(self, *_):
        dialog = Adw.Window(
            title="Создать контейнер",
            transient_for=self,
            modal=True,
            default_width=400
        )
        
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12
        )
        dialog.set_content(content)
        
        name_entry = Adw.EntryRow(title="Имя контейнера:")
        image_entry = Adw.EntryRow(title="Образ Docker:", text="ubuntu:22.04")
        
        options_group = Adw.PreferencesGroup(title="Настройки")
        options_group.add(name_entry)
        options_group.add(image_entry)
        
        # features_group = Adw.PreferencesGroup(title="Опции")
        # home_mount = Gtk.CheckButton(label="Монтировать домашнюю папку")
        # x11_access = Gtk.CheckButton(label="Доступ к X11")
        # wayland_access = Gtk.CheckButton(label="Доступ к Wayland")
        # pulse_access = Gtk.CheckButton(label="Доступ к PulseAudio")
        
        # for w in [home_mount, x11_access, wayland_access, pulse_access]:
        #     features_group.add(w)
        
        btn_box = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        cancel_btn = Gtk.Button(label="Отмена")
        create_btn = Gtk.Button(label="Создать", css_classes=["suggested-action"])
        
        cancel_btn.connect("clicked", lambda *_: dialog.destroy())
        create_btn.connect("clicked", self.on_create_clicked, dialog, name_entry, image_entry, 
                        #   home_mount, x11_access, wayland_access, pulse_access)
        )
        
        btn_box.append(cancel_btn)
        btn_box.append(create_btn)
        
        content.append(options_group)
        # content.append(features_group)
        content.append(btn_box)
        dialog.present()
    
    def on_create_clicked(self, _, dialog, name_entry, image_entry, *options):
        name = name_entry.get_text()
        image = image_entry.get_text()
        
        if not name or not image:
            self.show_toast(dialog, "Заполните обязательные поля!")
            return
        
        dialog.destroy()
        self.task_queue = Queue()
        
        progress_dialog = CreateProgressDialog(self, self.task_queue)
        progress_dialog.cancel_btn.connect("clicked", lambda *_: self.task_queue.put((0, "Отмена операции...", True)))
        progress_dialog.present()
        
        thread = threading.Thread(
            target=self.create_container_async,
            args=(name, image, options),
            daemon=True
        )
        thread.start()
    
    def create_container_async(self, name, image, options):
        args = ["distrobox", "create", "--name", name, "--image", image]
        opts_map = ["--home", "--x11", "--wayland", "--pulseaudio"]
        for opt, widget in zip(opts_map, options):
            if widget.get_active():
                args.append(opt)
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,  # Добавлено для обработки ввода
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Автоматически подтверждаем загрузку образа
            process.stdin.write('Y\n')
            process.stdin.flush()

            # Отправка начального статуса
            self.task_queue.put((0.1, "Запуск процесса создания...", False))
            
            # Чтение вывода в реальном времени
            for line in iter(process.stdout.readline, ''):
                GLib.idle_add(
                    self.task_queue.put, 
                    line.strip() + "\n"
                )
            process.wait()
            if process.returncode == 0:
                self.task_queue.put((1.0, "Контейнер успешно создан!", True))
                GLib.idle_add(self.refresh_containers)
            else:
                self.task_queue.put((0, f"Ошибка (код: {process.returncode})", True))
        except Exception as e:
            self.task_queue.put((0, f"Исключение: {str(e)}", True))
    
    def show_toast(self, dialog, message):
        toast = Adw.Toast(title=message, timeout=2)
        dialog.add_toast(toast)
    
    def show_error(self, message):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Ошибка",
            body=message
        )
        dialog.add_response("ok", "OK")
        dialog.connect("response", lambda d, _: d.destroy())
        dialog.present()

class DistroboxApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
    
    def do_activate(self):
        win = DistroboxManager(self)
        win.present()

if __name__ == "__main__":
    app = DistroboxApp()
    app.run()