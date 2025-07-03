import tkinter as tk
from tkinter import filedialog, messagebox, Canvas, Scrollbar, simpledialog, colorchooser
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import os
import platform
import subprocess
import tempfile

class TextPropertiesDialog(simpledialog.Dialog):
    def __init__(self, parent, title="Text Properties"):
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        tk.Label(master, text="Text:").grid(row=0, sticky='w')
        self.text_entry = tk.Entry(master, width=40)
        self.text_entry.grid(row=0, column=1)
        tk.Label(master, text="Font:").grid(row=1, sticky='w')
        self.font_var = tk.StringVar(value='Helvetica')
        fonts = ('Helvetica', 'Courier', 'Times-Roman')
        self.font_menu = tk.OptionMenu(master, self.font_var, *fonts)
        self.font_menu.grid(row=1, column=1, sticky='ew')
        tk.Label(master, text="Size:").grid(row=2, sticky='w')
        self.size_var = tk.IntVar(value=12)
        self.size_spinbox = tk.Spinbox(master, from_=8, to=72, textvariable=self.size_var)
        self.size_spinbox.grid(row=2, column=1, sticky='ew')
        tk.Label(master, text="Color:").grid(row=3, sticky='w')
        self.color_button = tk.Button(master, text='Choose Color', command=self.choose_color)
        self.color_button.grid(row=3, column=1, sticky='ew')
        self.color_label = tk.Label(master, text="#000000", bg="#000000", fg="#ffffff")
        self.color_label.grid(row=4, columnspan=2, sticky='ew')
        self.color_rgb = (0, 0, 0)
        self.color_hex = "#000000"
        return self.text_entry

    def choose_color(self):
        color_code = colorchooser.askcolor(title="Choose color")
        if color_code:
            self.color_rgb, self.color_hex = color_code
            self.color_label.config(bg=self.color_hex, text=self.color_hex, fg=self.get_text_color(self.color_rgb))

    def get_text_color(self, rgb):
        r, g, b = [x / 255.0 for x in rgb]
        return '#000000' if (r * 0.299 + g * 0.587 + b * 0.114) > 0.6 else '#ffffff'

    def apply(self):
        text = self.text_entry.get()
        if not text:
            messagebox.showwarning("Input Error", "Text cannot be empty.")
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
        self.root.title("PDF Editor")
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = Canvas(main_frame, bg="#606060")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.v_scrollbar = Scrollbar(main_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set)
        self.h_scrollbar = Scrollbar(root, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.configure(xscrollcommand=self.h_scrollbar.set)
        
        # State variables
        self.zoom_level = 1.0
        self.zoom_step = 0.5
        self.pil_images_for_embed = {}
        self.current_action = None
        self.resizing_rect_id = None
        
        self.create_menu()
        self.reset_state()

        self.canvas.bind('<Configure>', self.on_canvas_configure)
        self.root.bind('<Escape>', self.cancel_current_action_event)
        self.root.bind('<Control-z>', self.undo_last_action_event)
        self.root.bind('<Control-plus>', self.zoom_in)
        self.root.bind('<Control-minus>', self.zoom_out)
        self.root.bind('<Command-plus>', self.zoom_in) # for macOS
        self.root.bind('<Command-minus>', self.zoom_out) # for macOS
        self.root.bind('<Command-z>', self.undo_last_action_event) # for macOS


    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        # File Menu
        self.file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=self.file_menu)
        self.file_menu.add_command(label="Open PDF", command=self.open_pdf)
        self.file_menu.add_command(label="Save PDF As...", command=self.save_pdf)
        self.file_menu.add_command(label="View to Print...", command=self.print_pdf)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.root.quit)
        # Edit Menu
        self.edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=self.edit_menu)
        self.edit_menu.add_command(label="Add Image...", command=self.toggle_image_placement)
        self.edit_menu.add_command(label="Add Text...", command=self.toggle_text_placement)
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Undo", command=self.undo_last_action, accelerator="Ctrl+Z")
        # View Menu
        self.view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=self.view_menu)
        self.view_menu.add_command(label="Zoom In", command=self.zoom_in, accelerator="Ctrl++")
        self.view_menu.add_command(label="Zoom Out", command=self.zoom_out, accelerator="Ctrl+-")

    def reset_state(self):
        self.canvas.delete("all")
        if hasattr(self, 'pdf_document') and self.pdf_document:
            self.pdf_document.close()
        self.pdf_document = None
        self.file_path = None
        self.page_layout_info = []
        self.tkinter_objects = []
        self.images_to_embed = []
        self.text_to_embed = []
        self.action_history = []
        self.zoom_level = 1.0
        self.cancel_current_action()
        self.update_menu_states()

    def update_menu_states(self, action_in_progress=None):
        is_pdf_loaded = self.pdf_document is not None
        base_state = tk.NORMAL if is_pdf_loaded else tk.DISABLED
        
        self.file_menu.entryconfig("Save PDF As...", state=base_state)
        self.view_menu.entryconfig("Zoom In", state=base_state)
        self.view_menu.entryconfig("Zoom Out", state=base_state if self.zoom_level > self.zoom_step else tk.DISABLED)

        if action_in_progress == 'image':
            self.edit_menu.entryconfig(0, label="Cancel Image Placement", state=tk.NORMAL)
            self.edit_menu.entryconfig(1, state=tk.DISABLED)
        elif action_in_progress == 'text':
            self.edit_menu.entryconfig(0, state=tk.DISABLED)
            self.edit_menu.entryconfig(1, label="Cancel Text Placement", state=tk.NORMAL)
        else:
            self.edit_menu.entryconfig(0, label="Add Image...", state=base_state)
            self.edit_menu.entryconfig(1, label="Add Text...", state=base_state)

        self.edit_menu.entryconfig(3, state=tk.NORMAL if self.action_history else tk.DISABLED)

    def on_canvas_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def open_pdf(self):
        if self.current_action: self.cancel_current_action()
        file_path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if not file_path: return
        self.reset_state()
        self.file_path = file_path
        try:
            self.pdf_document = fitz.open(file_path)
            for page_num in range(len(self.pdf_document)):
                page = self.pdf_document.load_page(page_num)
                self.page_layout_info.append({'original_width': page.rect.width, 'original_height': page.rect.height})
            self.redraw_canvas()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open PDF: {e}")
            self.reset_state()

    def redraw_canvas(self):
        self.canvas.delete("all")
        self.tkinter_objects = []
        y_offset = 10

        if not self.pdf_document:
            return

        for page_num, page_info in enumerate(self.page_layout_info):
            page = self.pdf_document.load_page(page_num)
            mat = fitz.Matrix(self.zoom_level, self.zoom_level)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            tk_img = ImageTk.PhotoImage(img)
            self.tkinter_objects.append(tk_img)
            
            page_x, page_y = 10, y_offset
            self.canvas.create_image(page_x, page_y, image=tk_img, anchor='nw', tags=f"page_{page_num}")
            page_info.update({'page_num': page_num, 'x': page_x, 'y': page_y, 'width': pix.width, 'height': pix.height})
            y_offset += pix.height + 10

        # Redraw embedded objects
        for item in self.action_history:
            action_type = item['type']
            if action_type == 'image':
                self.draw_embedded_image(item['data'])
            elif action_type == 'text':
                self.draw_embedded_text(item['data'])
        
        self.on_canvas_configure(None)
        self.update_menu_states()

    def draw_embedded_image(self, img_data):
        page_info = self.page_layout_info[img_data['page_num']]
        x = page_info['x'] + img_data['rel_x'] * self.zoom_level
        y = page_info['y'] + img_data['rel_y'] * self.zoom_level
        w = img_data['width'] * self.zoom_level
        h = img_data['height'] * self.zoom_level

        if img_data['path'] not in self.pil_images_for_embed:
             self.pil_images_for_embed[img_data['path']] = Image.open(img_data['path'])
        pil_img = self.pil_images_for_embed[img_data['path']]
        
        if int(w) > 0 and int(h) > 0:
            resized_img = pil_img.resize((int(w), int(h)), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(resized_img)
            self.tkinter_objects.append(tk_img)
            self.canvas.create_image(x, y, image=tk_img, anchor='nw')

    def draw_embedded_text(self, text_data):
        page_info = self.page_layout_info[text_data['page_num']]
        x = page_info['x'] + text_data['rel_x'] * self.zoom_level
        y = page_info['y'] + text_data['rel_y'] * self.zoom_level
        font_size = int(text_data['size'] * self.zoom_level)
        self.canvas.create_text(x, y, text=text_data['text'], font=(text_data['font'], font_size), fill=text_data['hex_color'], anchor='nw')

    def zoom_in(self, event=None):
        if not self.pdf_document: return
        self.zoom_level += self.zoom_step
        self.redraw_canvas()

    def zoom_out(self, event=None):
        if not self.pdf_document or self.zoom_level <= self.zoom_step: return
        self.zoom_level -= self.zoom_step
        self.redraw_canvas()

    def toggle_image_placement(self):
        if self.current_action == 'image':
            self.cancel_current_action()
            return
        self.cancel_current_action()
        image_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png")])
        if not image_path: return

        try:
            self.current_action = 'image'
            self.pil_image_to_place = Image.open(image_path)
            self.image_path_to_embed = image_path
            self.root.title(f"PDF Editor - Draw rectangle for: {os.path.basename(image_path)}")
            self.canvas.config(cursor="crosshair")
            self.update_menu_states(action_in_progress='image')
            self.canvas.bind("<ButtonPress-1>", self.start_resize)
            self.canvas.bind("<B1-Motion>", self.do_resize)
            self.canvas.bind("<ButtonRelease-1>", self.end_resize)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image: {e}")
            self.cancel_current_action()

    def toggle_text_placement(self):
        if self.current_action == 'text':
            self.cancel_current_action()
            return
        self.cancel_current_action()
        self.current_action = 'text'
        self.root.title("PDF Editor - Click to add text")
        self.canvas.config(cursor="xterm")
        self.update_menu_states(action_in_progress='text')
        self.canvas.bind("<ButtonPress-1>", self.handle_text_click)

    def cancel_current_action_event(self, event=None):
        if self.current_action:
            self.cancel_current_action()
        return "break"
    
    def cancel_current_action(self):
        self.canvas.unbind("<ButtonPress-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        if self.resizing_rect_id:
            self.canvas.delete(self.resizing_rect_id)
        self.pil_image_to_place = None
        self.resizing_rect_id = None
        self.current_action = None
        self.root.title("PDF Editor")
        self.canvas.config(cursor="")
        self.update_menu_states()

    def start_resize(self, event):
        if self.current_action != 'image': return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.resizing_start_coords = (x, y)
        self.resizing_rect_id = self.canvas.create_rectangle(x, y, x, y, outline="red", dash=(2, 2))

    def do_resize(self, event):
        if not self.resizing_rect_id: return
        x0, y0 = self.resizing_start_coords
        x1, y1 = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.canvas.coords(self.resizing_rect_id, x0, y0, x1, y1)

    def end_resize(self, event):
        if not self.resizing_rect_id: return
        x0, y0, x1, y1 = self.canvas.coords(self.resizing_rect_id)
        self.canvas.delete(self.resizing_rect_id)
        self.resizing_rect_id = None
        
        start_x, end_x = min(x0, x1), max(x0, x1)
        start_y, end_y = min(y0, y1), max(y0, y1)
        
        target_page_info = self.get_page_at_coords(start_x, start_y)
        if not target_page_info:
            messagebox.showwarning("Placement Error", "Please draw the rectangle on a page.")
            self.cancel_current_action()
            return

        # Calculate coordinates relative to the page at 100% zoom
        rel_x = (start_x - target_page_info['x']) / self.zoom_level
        rel_y = (start_y - target_page_info['y']) / self.zoom_level
        width = (end_x - start_x) / self.zoom_level
        height = (end_y - start_y) / self.zoom_level

        if width < 5 or height < 5:
            messagebox.showwarning("Placement Error", "Image is too small.")
            self.cancel_current_action()
            return
        
        img_data = {
            'page_num': target_page_info['page_num'], 'rel_x': rel_x, 'rel_y': rel_y,
            'width': width, 'height': height, 'path': self.image_path_to_embed
        }
        self.images_to_embed.append(img_data)
        self.action_history.append({'type': 'image', 'data': img_data})
        self.cancel_current_action()
        self.redraw_canvas()

    def handle_text_click(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        target_page_info = self.get_page_at_coords(canvas_x, canvas_y)
        if not target_page_info:
            messagebox.showwarning("Placement Error", "Please click on a page to add text.")
            self.cancel_current_action()
            return

        self.cancel_current_action()
        dialog = TextPropertiesDialog(self.root)
        if dialog.result:
            res = dialog.result
            rel_x = (canvas_x - target_page_info['x']) / self.zoom_level
            rel_y = (canvas_y - target_page_info['y']) / self.zoom_level
            
            text_data = {
                'page_num': target_page_info['page_num'], 'rel_x': rel_x, 'rel_y': rel_y,
                'text': res['text'], 'font': res['font'], 'size': res['size'],
                'color': res['color'], 'hex_color': res['hex_color']
            }
            self.text_to_embed.append(text_data)
            self.action_history.append({'type': 'text', 'data': text_data})
            self.redraw_canvas()

    def get_page_at_coords(self, x, y):
        for info in self.page_layout_info:
            if info['x'] <= x < info['x'] + info['width'] and info['y'] <= y < info['y'] + info['height']:
                return info
        return None

    def undo_last_action_event(self, event=None):
        self.undo_last_action()
        return "break"

    def undo_last_action(self):
        if not self.action_history: return
        
        last_action = self.action_history.pop()
        action_type = last_action['type']
        
        if action_type == 'image':
            self.images_to_embed.pop()
        elif action_type == 'text':
            self.text_to_embed.pop()
            
        self.redraw_canvas()

    def save_pdf(self):
        if self.current_action: self.cancel_current_action()
        if not self.pdf_document or not self.file_path: return
        
        save_path = filedialog.asksaveasfilename(
            initialdir=os.path.dirname(self.file_path),
            initialfile=f"{os.path.splitext(os.path.basename(self.file_path))[0]}_edited.pdf",
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")]
        )
        if not save_path: return

        if self._save_document(save_path):
            messagebox.showinfo("Success", f"PDF saved successfully to {save_path}")

    def _save_document(self, save_path):
        try:
            doc = fitz.open(self.file_path)
            for img_data in self.images_to_embed:
                page = doc.load_page(img_data['page_num'])
                img_rect = fitz.Rect(img_data['rel_x'], img_data['rel_y'], 
                                     img_data['rel_x'] + img_data['width'], img_data['rel_y'] + img_data['height'])
                page.insert_image(img_rect, filename=img_data['path'], overlay=True)
            
            for text_data in self.text_to_embed:
                page = doc.load_page(text_data['page_num'])
                point = fitz.Point(text_data['rel_x'], text_data['rel_y'] + text_data['size'])
                font_map = {'helvetica': 'helv', 'courier': 'cour', 'times-roman': 'tiro'}
                fitz_font_name = font_map.get(text_data['font'].lower(), 'helv')
                page.insert_text(point, text_data['text'], fontname=fitz_font_name, fontsize=text_data['size'], color=text_data['color'])

            doc.save(save_path, garbage=4, deflate=True, clean=True)
            doc.close()
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save PDF: {e}")
            return False

    def print_pdf(self):
        if self.current_action: self.cancel_current_action()
        if not self.pdf_document:
            messagebox.showwarning("Print Error", "Please open a PDF file first.")
            return

        try:
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)

            if not self._save_document(temp_path):
                if os.path.exists(temp_path): os.unlink(temp_path)
                return

            current_os = platform.system()
            try:
                if current_os == "Windows":
                    os.startfile(temp_path)
                elif current_os == "Darwin":
                    subprocess.call(["open", temp_path])
                elif current_os == "Linux":
                    subprocess.call(["xdg-open", temp_path])
                else:
                    messagebox.showerror("Unsupported OS", f"Printing is not supported on {current_os}.")
                    if os.path.exists(temp_path): os.unlink(temp_path)
                    return
                
                messagebox.showinfo("Print", "The PDF has been opened in your default viewer. Please use its print function (usually Ctrl+P or Cmd+P).")
            except Exception as e:
                messagebox.showerror("Error", f"Could not open the PDF file: {e}")
                # Clean up the temp file if opening fails
                if os.path.exists(temp_path): os.unlink(temp_path)

        except Exception as e:
            messagebox.showerror("Print Error", f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = PDFEditor(root)
    root.geometry("800x600")
    root.mainloop()