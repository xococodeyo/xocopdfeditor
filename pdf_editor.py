import tkinter as tk
from tkinter import filedialog, messagebox, Canvas, Scrollbar, simpledialog, colorchooser
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import os
import platform
import subprocess
import tempfile
import json

class TextPropertiesDialog(simpledialog.Dialog):
    def __init__(self, parent, translator):
        self._ = translator
        self.result = None
        super().__init__(parent, self._("text_properties_title"))

    def body(self, master):
        tk.Label(master, text=self._("text_prop_text")).grid(row=0, sticky='w')
        self.text_entry = tk.Entry(master, width=40)
        self.text_entry.grid(row=0, column=1)
        
        tk.Label(master, text=self._("text_prop_font")).grid(row=1, sticky='w')
        self.font_var = tk.StringVar(value='Helvetica')
        fonts = ('Helvetica', 'Courier', 'Times-Roman')
        self.font_menu = tk.OptionMenu(master, self.font_var, *fonts)
        self.font_menu.grid(row=1, column=1, sticky='ew')

        tk.Label(master, text=self._("text_prop_size")).grid(row=2, sticky='w')
        self.size_var = tk.IntVar(value=12)
        self.size_spinbox = tk.Spinbox(master, from_=8, to=72, textvariable=self.size_var)
        self.size_spinbox.grid(row=2, column=1, sticky='ew')

        tk.Label(master, text=self._("text_prop_color")).grid(row=3, sticky='w')
        self.color_button = tk.Button(master, text=self._('choose_color'), command=self.choose_color)
        self.color_button.grid(row=3, column=1, sticky='ew')
        self.color_label = tk.Label(master, text="#000000", bg="#000000", fg="#ffffff")
        self.color_label.grid(row=4, columnspan=2, sticky='ew')
        self.color_rgb = (0, 0, 0)
        self.color_hex = "#000000"

        return self.text_entry

    def choose_color(self):
        color_code = colorchooser.askcolor(title=self._("choose_color_title"))
        if color_code and color_code[0]:
            self.color_rgb = color_code[0]
            self.color_hex = color_code[1]
            self.color_label.config(bg=self.color_hex, text=self.color_hex, fg=self.get_text_color(self.color_rgb))

    def get_text_color(self, rgb):
        r, g, b = [x / 255.0 for x in rgb]
        return '#000000' if (r * 0.299 + g * 0.587 + b * 0.114) > 0.6 else '#ffffff'

    def apply(self):
        text = self.text_entry.get()
        if not text:
            messagebox.showwarning(self._("input_error_title"), self._("text_cannot_be_empty"))
            return
        self.result = {
            'text': text,
            'font': self.font_var.get(),
            'size': self.size_var.get(),
            'color': tuple(c / 255 for c in self.color_rgb),
            'hex_color': self.color_hex
        }

class PDFEditor:
    def __init__(self, root):
        self.root = root
        self._load_translations()
        self.language = 'en' # Default language
        self.language_var = tk.StringVar(value=self.language)

        self.root.geometry("1000x800")
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.pdf_document = None
        self.file_path = None
        self.images_to_embed = []
        self.text_to_embed = []
        self.action_history = []
        self.page_displays = []
        self.page_layout_info = []
        self.current_page_num = 0
        self.zoom_level = 1.0

        self.current_action = None
        self.pil_image_to_place = None
        self.resizing_rect_id = None
        self.start_x = 0
        self.start_y = 0

        self.text_data_to_place = None
        self.text_preview_id = None

        self._create_widgets()
        self._update_ui_text()
        self.update_ui_states()

    def _load_translations(self):
        try:
            with open('translations.json', 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.translations = {}
            messagebox.showerror("Error", f"Could not load translations file: {e}")

    def _(self, key):
        return self.translations.get(self.language, {}).get(key, key)

    def _change_language(self, lang_code):
        self.language = lang_code
        self.language_var.set(lang_code)
        self._update_ui_text()

    def _create_widgets(self):
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)

        # Create menus - they will be populated in _update_ui_text
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.edit_menu = tk.Menu(self.menubar, tearoff=0)
        self.view_menu = tk.Menu(self.menubar, tearoff=0)
        self.language_menu = tk.Menu(self.menubar, tearoff=0)

        self.menubar.add_cascade(label="File", menu=self.file_menu) # Placeholder label
        self.menubar.add_cascade(label="Edit", menu=self.edit_menu)
        self.menubar.add_cascade(label="View", menu=self.view_menu)
        self.menubar.add_cascade(label="Language", menu=self.language_menu)

        # Toolbar
        toolbar = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        self.add_image_button = tk.Button(toolbar, command=self.toggle_image_placement)
        self.add_image_button.pack(side=tk.LEFT, padx=2, pady=2)
        self.add_text_button = tk.Button(toolbar, command=self.toggle_text_placement)
        self.add_text_button.pack(side=tk.LEFT, padx=2, pady=2)

        zoom_out_button = tk.Button(toolbar, text="-", command=lambda: self.zoom(0.8))
        zoom_out_button.pack(side=tk.LEFT, padx=2, pady=2)

        self.zoom_label = tk.Label(toolbar, text="100%", width=5)
        self.zoom_label.pack(side=tk.LEFT, padx=2, pady=2)

        zoom_in_button = tk.Button(toolbar, text="+", command=lambda: self.zoom(1.2))
        zoom_in_button.pack(side=tk.LEFT, padx=2, pady=2)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        # Main Frame with Canvas and Scrollbar
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=1)

        self.canvas = Canvas(main_frame, bg="#f0f0f0")
        self.v_scrollbar = Scrollbar(main_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scrollbar = Scrollbar(self.root, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.config(yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)

        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

        # Status Bar
        self.status_bar = tk.Frame(self.root, bd=1, relief=tk.SUNKEN)
        self.page_label = tk.Label(self.status_bar, text="", width=20)
        self.page_label.pack(side=tk.RIGHT, padx=2, pady=2)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Bindings
        control_key = "Command" if platform.system() == "Darwin" else "Control"
        self.root.bind(f"<{control_key}-z>", lambda event: self.undo_last_action())
        self.root.bind(f"<{control_key}-plus>", lambda event: self.zoom(1.2))
        self.root.bind(f"<{control_key}-minus>", lambda event: self.zoom(0.8))
        self.root.bind(f"<{control_key}-0>", lambda event: self.reset_zoom())

    def _update_ui_text(self):
        self.root.title(self._("app_title"))

        # --- Rebuild Menus --- #

        # Update menubar cascade labels (indices are stable)
        self.menubar.entryconfig(0, label=self._("file_menu"))
        self.menubar.entryconfig(1, label=self._("edit_menu"))
        self.menubar.entryconfig(2, label=self._("view_menu"))
        self.menubar.entryconfig(3, label=self._("language_menu"))

        # Rebuild File menu
        self.file_menu.delete(0, tk.END)
        self.file_menu.add_command(label=self._("open_pdf"), command=self.open_pdf)
        self.file_menu.add_command(label=self._("save_pdf"), command=self._save_document)
        self.file_menu.add_command(label=self._("save_as_pdf"), command=self._save_as_document)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._("print_pdf"), command=self.print_pdf)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._("exit_app"), command=self._on_closing)

        # Rebuild Edit menu
        self.edit_menu.delete(0, tk.END)
        self.edit_menu.add_command(label=self._("undo"), command=self.undo_last_action)
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label=self._("add_image"), command=self.toggle_image_placement)
        self.edit_menu.add_command(label=self._("add_text"), command=self.toggle_text_placement)
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label=self._("cancel_action"), command=self.cancel_current_action)

        # Rebuild View menu
        self.view_menu.delete(0, tk.END)
        self.view_menu.add_command(label=self._("zoom_in"), command=lambda: self.zoom(1.2))
        self.view_menu.add_command(label=self._("zoom_out"), command=lambda: self.zoom(0.8))
        self.view_menu.add_command(label=self._("zoom_reset"), command=self.reset_zoom)

        # Rebuild Language menu
        self.language_menu.delete(0, tk.END)
        for lang_code in sorted(self.translations.keys()):
            if isinstance(self.translations[lang_code], dict):
                lang_name_key = f"lang_{lang_code}"
                lang_name = self._(lang_name_key)
                self.language_menu.add_radiobutton(
                    label=lang_name,
                    variable=self.language_var,
                    value=lang_code,
                    command=lambda lc=lang_code: self._change_language(lc)
                )

        # Update toolbar buttons
        self.add_image_button.config(text=self._("add_image"))
        self.add_text_button.config(text=self._("add_text"))

        # Update status bar
        if self.pdf_document:
            self.page_label.config(text=self._("page_status").format(self.current_page_num + 1, self.pdf_document.page_count))
        else:
            self.page_label.config(text=self._("no_pdf_open"))

        self.update_ui_states()

    def update_ui_states(self):
        base_state = tk.NORMAL if self.pdf_document else tk.DISABLED

        # File Menu
        self.file_menu.entryconfig(1, state=base_state)  # Save
        self.file_menu.entryconfig(2, state=base_state)  # Save As
        self.file_menu.entryconfig(4, state=base_state)  # Print

        # Edit Menu
        self.edit_menu.entryconfig(0, state=tk.NORMAL if self.action_history else tk.DISABLED) # Undo

        # View Menu (by index)
        self.view_menu.entryconfig(0, state=base_state)  # Zoom In
        self.view_menu.entryconfig(1, state=base_state)  # Zoom Out
        self.view_menu.entryconfig(2, state=base_state)  # Reset Zoom

        self.add_image_button.config(state=base_state)
        self.add_text_button.config(state=base_state)

        if self.current_action == 'image':
            self.add_image_button.config(text=self._("cancel"))
            self.add_text_button.config(state=tk.DISABLED)
            self.edit_menu.entryconfig(3, state=tk.DISABLED)  # Add Text
            self.edit_menu.entryconfig(2, label=self._("cancel_image_placement"))  # Add Image
        elif self.current_action == 'text':
            self.add_text_button.config(text=self._("cancel"))
            self.add_image_button.config(state=tk.DISABLED)
            self.edit_menu.entryconfig(2, state=tk.DISABLED)  # Add Image
            self.edit_menu.entryconfig(3, label=self._("cancel_text_placement"))  # Add Text
        else:
            self.add_image_button.config(text=self._("add_image"))
            self.add_text_button.config(text=self._("add_text"))
            self.edit_menu.entryconfig(2, state=base_state, label=self._("add_image"))
            self.edit_menu.entryconfig(3, state=base_state, label=self._("add_text"))

    def open_pdf(self):
        filepath = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if not filepath:
            return
        try:
            self.file_path = filepath
            self.pdf_document = fitz.open(filepath)
            self.current_page_num = 0
            self.action_history = []
            self.images_to_embed = []
            self.text_to_embed = []
            self.page_layout_info = [{'original_width': p.rect.width, 'original_height': p.rect.height} for p in self.pdf_document]
            self.display_pages()
            self.update_ui_states()
        except Exception as e:
            messagebox.showerror(self._("error_title"), f"Failed to open PDF: {e}")

    def display_pages(self):
        self.canvas.delete("all")
        self.page_displays = []
        y_offset = 10

        for i, page in enumerate(self.pdf_document):
            w, h = self.page_layout_info[i]['original_width'], self.page_layout_info[i]['original_height']
            render_width, render_height = int(w * self.zoom_level), int(h * self.zoom_level)

            pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom_level, self.zoom_level))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            tk_img = ImageTk.PhotoImage(image=img)

            page_x = (self.canvas.winfo_width() - render_width) / 2
            if page_x < 10: page_x = 10

            self.canvas.create_image(page_x, y_offset, anchor='nw', image=tk_img)
            self.page_displays.append({'image': tk_img, 'x': page_x, 'y': y_offset, 'w': render_width, 'h': render_height, 'page_num': i})
            y_offset += render_height + 10

        self.canvas.config(scrollregion=self.canvas.bbox("all"))
        self._redraw_embedded_objects()
        self._update_page_display()

    def _redraw_embedded_objects(self):
        for item in self.images_to_embed:
            self._draw_embedded_image(item)
        for item in self.text_to_embed:
            self._draw_embedded_text(item)

    def _draw_embedded_image(self, item):
        page_info = self.page_displays[item['page_num']]
        x = page_info['x'] + item['rel_x'] * self.zoom_level
        y = page_info['y'] + item['rel_y'] * self.zoom_level
        w = item['rel_w'] * self.zoom_level
        h = item['rel_h'] * self.zoom_level

        pil_img = Image.open(item['path'])
        pil_img = pil_img.resize((int(w), int(h)), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(image=pil_img)

        img_id = self.canvas.create_image(x, y, anchor='nw', image=tk_img)
        item['canvas_image_ref'] = tk_img
        item['canvas_id'] = img_id

    def _draw_embedded_text(self, item):
        page_info = self.page_displays[item['page_num']]
        x = page_info['x'] + item['rel_x'] * self.zoom_level
        y = page_info['y'] + item['rel_y'] * self.zoom_level
        
        font_size_canvas = int(item['size'] * self.zoom_level * (72/96))

        text_id = self.canvas.create_text(x, y, text=item['text'], 
                                          font=(item['font'], font_size_canvas), 
                                          fill=item['hex_color'], anchor='nw')
        item['canvas_id'] = text_id

    def _update_page_display(self):
        if self.pdf_document:
            page_text = self._("page_display").format(page_num=self.current_page_num + 1, total_pages=self.pdf_document.page_count)
            self.page_label.config(text=page_text)
        else:
            page_text = self._("page_display").format(page_num=0, total_pages=0)
            self.page_label.config(text=page_text)

    def zoom(self, factor):
        if not self.pdf_document: return
        self.zoom_level *= factor
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
        self.display_pages()

    def reset_zoom(self):
        if not self.pdf_document: return
        self.zoom_level = 1.0
        self.zoom_label.config(text="100%")
        self.display_pages()

    def get_page_at_coords(self, canvas_x, canvas_y):
        for page_info in self.page_displays:
            if page_info['x'] <= canvas_x <= page_info['x'] + page_info['w'] and \
               page_info['y'] <= canvas_y <= page_info['y'] + page_info['h']:
                return page_info
        return None

    def toggle_image_placement(self):
        if self.current_action == 'image':
            self.cancel_current_action()
            return

        self.cancel_current_action()
        filepath = filedialog.askopenfilename(
            filetypes=[(self._("image_files"), "*.png *.jpg *.jpeg *.bmp *.gif"), (self._("all_files"), "*.*")]
        )
        if not filepath: return

        try:
            self.pil_image_to_place = Image.open(filepath)
            self.current_action = 'image'
            self.root.title(self._("main_title") + f" - {self._('place_image_prompt')}")
            self.canvas.config(cursor="crosshair")
            self.update_ui_states()
            self.canvas.bind("<ButtonPress-1>", self.start_resize)
            self.canvas.bind("<B1-Motion>", self.do_resize)
            self.canvas.bind("<ButtonRelease-1>", self.end_resize)
        except Exception as e:
            messagebox.showerror(self._("error_title"), f"{self._('could_not_open_image')}: {e}")
            self.cancel_current_action()

    def toggle_text_placement(self):
        if self.current_action == 'text':
            self.cancel_current_action()
            return

        self.cancel_current_action()

        dialog = TextPropertiesDialog(self.root, self._)
        if not dialog.result: return

        self.text_data_to_place = dialog.result
        self.current_action = 'text'
        self.root.title(self._("main_title") + f" - {self._('place_text_prompt')}")
        self.canvas.config(cursor="tcross")
        self.update_ui_states()

        self.canvas.bind("<Motion>", self.update_text_preview)
        self.canvas.bind("<ButtonPress-1>", self.finalize_text_placement)
        self.canvas.bind("<Enter>", self.update_text_preview)
        self.canvas.bind("<Leave>", self.clear_text_preview)

    def cancel_current_action(self):
        self.canvas.unbind("<ButtonPress-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        self.canvas.unbind("<Motion>")
        self.canvas.unbind("<Enter>")
        self.canvas.unbind("<Leave>")

        if self.resizing_rect_id: self.canvas.delete(self.resizing_rect_id)
        self.clear_text_preview()

        self.pil_image_to_place = None
        self.resizing_rect_id = None
        self.current_action = None
        self.text_data_to_place = None

        self.root.title(self._("main_title"))
        self.canvas.config(cursor="")
        self.update_ui_states()

    def start_resize(self, event):
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        self.resizing_rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red', dash=(4, 4))

    def do_resize(self, event):
        cur_x, cur_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.canvas.coords(self.resizing_rect_id, self.start_x, self.start_y, cur_x, cur_y)

    def end_resize(self, event):
        end_x, end_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        target_page_info = self.get_page_at_coords(self.start_x, self.start_y)
        if not target_page_info:
            messagebox.showwarning(self._("placement_error_title"), self._("place_on_page_warning"))
            self.cancel_current_action()
            return

        rel_x = (min(self.start_x, end_x) - target_page_info['x']) / self.zoom_level
        rel_y = (min(self.start_y, end_y) - target_page_info['y']) / self.zoom_level
        rel_w = abs(end_x - self.start_x) / self.zoom_level
        rel_h = abs(end_y - self.start_y) / self.zoom_level

        if rel_w < 5 or rel_h < 5:
            messagebox.showwarning(self._("placement_error_title"), self._("image_too_small"))
            self.cancel_current_action()
            return

        image_data = {
            'type': 'image',
            'path': self.pil_image_to_place.filename,
            'page_num': target_page_info['page_num'],
            'rel_x': rel_x, 'rel_y': rel_y, 'rel_w': rel_w, 'rel_h': rel_h
        }

        self.images_to_embed.append(image_data)
        self.action_history.append({'type': 'image', 'data': image_data})
        self._draw_embedded_image(image_data)
        self.cancel_current_action()

    def update_text_preview(self, event):
        self.clear_text_preview()
        if not self.text_data_to_place: return

        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        font_size_canvas = int(self.text_data_to_place['size'] * self.zoom_level * (72/96))

        text_id = self.canvas.create_text(canvas_x, canvas_y, text=self.text_data_to_place['text'],
                                          font=(self.text_data_to_place['font'], font_size_canvas),
                                          fill=self.text_data_to_place['hex_color'], anchor='nw')
        bbox = self.canvas.bbox(text_id)
        if bbox:
            rect_id = self.canvas.create_rectangle(bbox, dash=(4, 4), outline='gray')
            self.text_preview_id = (text_id, rect_id)

    def clear_text_preview(self):
        if self.text_preview_id:
            self.canvas.delete(self.text_preview_id[0])
            self.canvas.delete(self.text_preview_id[1])
            self.text_preview_id = None

    def finalize_text_placement(self, event):
        if not self.text_data_to_place: return

        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        target_page_info = self.get_page_at_coords(canvas_x, canvas_y)

        if not target_page_info:
            messagebox.showwarning(self._("placement_error_title"), self._("place_on_page_warning"))
            self.cancel_current_action()
            return

        rel_x = (canvas_x - target_page_info['x']) / self.zoom_level
        rel_y = (canvas_y - target_page_info['y']) / self.zoom_level

        final_text_data = self.text_data_to_place.copy()
        final_text_data.update({
            'page_num': target_page_info['page_num'], 
            'rel_x': rel_x, 'rel_y': rel_y
        })

        self.text_to_embed.append(final_text_data)
        self.action_history.append({'type': 'text', 'data': final_text_data})
        self.cancel_current_action()
        self._draw_embedded_text(final_text_data)

    def undo_last_action(self):
        if not self.action_history: return

        last_action = self.action_history.pop()
        if last_action['type'] == 'image':
            removed_item = self.images_to_embed.pop()
            if 'canvas_id' in removed_item: self.canvas.delete(removed_item['canvas_id'])
        elif last_action['type'] == 'text':
            removed_item = self.text_to_embed.pop()
            if 'canvas_id' in removed_item: self.canvas.delete(removed_item['canvas_id'])
        
        self.update_ui_states()

    def _save_document(self):
        if not self.file_path:
            return self._save_as_document()
        return self._perform_save(self.file_path)

    def _save_as_document(self):
        if not self.pdf_document: return False
        save_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")]
        )
        if not save_path: return False
        return self._perform_save(save_path)

    def _perform_save(self, save_path, is_temporary_save=False):
        try:
            doc = fitz.open(self.file_path)

            for item in self.images_to_embed:
                page = doc.load_page(item['page_num'])
                rect = fitz.Rect(item['rel_x'], item['rel_y'], 
                                 item['rel_x'] + item['rel_w'], 
                                 item['rel_y'] + item['rel_h'])
                page.insert_image(rect, filename=item['path'])

            for item in self.text_to_embed:
                page = doc.load_page(item['page_num'])
                point = fitz.Point(item['rel_x'], item['rel_y'] + item['size'])
                page.insert_text(point, item['text'], 
                                  fontname=item['font'].lower(), 
                                  fontsize=item['size'], 
                                  color=item['color'])

            if save_path == self.file_path:
                doc.save(save_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
            else:
                doc.save(save_path)
            doc.close()

            if not is_temporary_save:
                self.action_history.clear()
                self.update_ui_states()
                messagebox.showinfo(self._("success_title"), f"{self._('pdf_saved_successfully_to')} {save_path}")
            
            return True
        except Exception as e:
            messagebox.showerror(self._("error_title"), f"{self._('failed_to_save_pdf')}: {e}")
            return False

    def print_pdf(self):
        if not self.pdf_document:
            messagebox.showwarning(self._("print_error_title"), self._("open_pdf_first"))
            return

        # If there are changes, always save to a temporary file for printing
        if self.action_history:
            temp_fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(temp_fd)
            
            # Save to temp file without clearing history or showing message
            if not self._perform_save(temp_path, is_temporary_save=True):
                if os.path.exists(temp_path): os.unlink(temp_path)
                return
            filepath_to_print = temp_path
        else:
            # No changes, print the original file
            filepath_to_print = self.file_path

        try:
            current_os = platform.system()
            if current_os == "Windows":
                os.startfile(filepath_to_print, "print")
            elif current_os == "Darwin": # macOS
                subprocess.call(["open", filepath_to_print])
            elif current_os == "Linux":
                subprocess.call(["xdg-open", filepath_to_print])
            else:
                messagebox.showerror(self._("unsupported_os_title"), f"{self._('printing_not_supported_on')} {current_os}.")
        except Exception as e:
            messagebox.showerror(self._("error_title"), f"{self._('could_not_open_print_dialog')}: {e}")
        finally:
            if 'temp_path' in locals() and filepath_to_print == temp_path and os.path.exists(temp_path):
                self.root.after(5000, lambda: os.unlink(temp_path))


    def _on_closing(self):
        if self.action_history:
            response = messagebox.askyesnocancel(self._("confirm_exit_title"), self._("save_changes_prompt"))
            if response is True:
                if self._save_document():
                    self.root.destroy()
            elif response is False:
                self.root.destroy()
        else:
            self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = PDFEditor(root)
    root.mainloop()
