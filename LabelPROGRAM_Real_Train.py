## non TOYOTA INTERN 2025 ##
## Dataset Label Tool  for YOLOv8 format (x,y,w,h) ##
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import pathlib
import subprocess
import sys

class YOLOLabelTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Dataset Label Tool")
        self.root.state('zoomed')

        self.dataset_path = ""
        self.image_list = []
        self.current_image_index = 0
        self.current_image_path = ""
        self.tk_image = None
        self.has_unsaved_changes = False  # Track unsaved changes

        # Add image position and size tracking
        self.image_x = 0  # Image position on canvas
        self.image_y = 0
        self.display_width = 0  # Displayed image size
        self.display_height = 0
        self.original_width = 0  # Original image dimensions
        self.original_height = 0

        self.class_file = ""
        self.class_names = []
        self.annotations = []
        self.rect_ids = []
        self.label_ids = []

        self.undo_stack = []  # stores dicts with box info
        self.redo_stack = []

        self.annotation_mode = False
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.temp_boxes = []

        # Drawing mode: 'bbox' or 'seg'
        self.draw_mode = 'bbox'

        # Segmentation (polygon) state
        self.seg_points = []
        self.seg_point_ids = []
        self.seg_segment_ids = []
        self.seg_preview_line_id = None
        self.seg_close_preview_id = None
        self.seg_poly_ids = []
        self.seg_label_ids = []
        self.seg_annotations = []  # (cls_id, [x1,y1,x2,y2,...] normalized)

        self.selected_box_id = None
        self.selected_label_id = None
        self.selected_shape_kind = 'bbox'
        self.drag_start_coords = None
        self.clipboard_boxes = []  # list of (w, h) tuples

        self.multi_selected_boxes = []  # holds multiple selected box IDs

        self.dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        self.setup_ui()

    def setup_ui(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        tk.Button(top_frame, text="Open Dir", command=self.open_directory).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="New Class", command=self.new_class_file).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Select Class File", command=self.select_class_file).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Edit Class", command=self.edit_class_file).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Change Class", command=self.change_class_for_selected_box).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="< Prev", command=self.prev_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Next >", command=self.next_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Undo", command=self.undo_annotation).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Redo", command=self.redo_annotation).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Save", command=self.save_annotations).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Select All", command=self.select_all_boxes).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Help", command=self.show_help).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="YOLOv8 Train", command=self.run_training_script).pack(side=tk.LEFT, padx=5)

        self.draw_mode_button = tk.Button(top_frame, text="Draw: BBOX", command=self.cycle_draw_mode)
        self.draw_mode_button.pack(side=tk.LEFT, padx=5)

        # Copy BBOX labels to another image (.txt)
        self.copy_target_var = tk.StringVar(value="")
        self.copy_target_menu = tk.OptionMenu(top_frame, self.copy_target_var, "")
        self.copy_target_menu.config(width=25)
        # (dropdown kept but not shown)
        tk.Button(top_frame, text="Copy Labels -> ALL", command=self.copy_labels_to_all_images).pack(side=tk.LEFT, padx=5)

        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.main_frame, bg='gray', width=900)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right_frame = tk.Frame(self.main_frame, width=500)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        # Image Files Section with horizontal scrollbar
        tk.Label(right_frame, text="Image Files", font=("Arial", 15, "bold")).pack()
        
        # Create frame for image listbox and its scrollbars
        image_list_frame = tk.Frame(right_frame)
        image_list_frame.pack(side=tk.TOP, fill=tk.X, padx=5)
        
        # Create vertical scrollbar for image listbox
        image_y_scroll = tk.Scrollbar(image_list_frame)
        image_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create horizontal scrollbar for image listbox
        image_x_scroll = tk.Scrollbar(image_list_frame, orient=tk.HORIZONTAL)
        image_x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Create image listbox with both scrollbars
        self.image_listbox = tk.Listbox(image_list_frame, height=20, width=22, 
                                      font=("Arial", 12), 
                                      xscrollcommand=image_x_scroll.set,
                                      yscrollcommand=image_y_scroll.set)
        self.image_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Configure scrollbar commands
        image_y_scroll.config(command=self.image_listbox.yview)
        image_x_scroll.config(command=self.image_listbox.xview)

        # Current Image Classes Section with horizontal scrollbar
        tk.Label(right_frame, text="Classes in Current Image", font=("Arial", 15, "bold")).pack(pady=(10,0))
        
        # Create frame for classes listbox and its scrollbars
        classes_list_frame = tk.Frame(right_frame)
        classes_list_frame.pack(side=tk.TOP, fill=tk.X, padx=5)
        
        # Create vertical scrollbar for classes listbox
        classes_y_scroll = tk.Scrollbar(classes_list_frame)
        classes_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create horizontal scrollbar for classes listbox
        classes_x_scroll = tk.Scrollbar(classes_list_frame, orient=tk.HORIZONTAL)
        classes_x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Create classes listbox with both scrollbars
        self.current_classes_listbox = tk.Listbox(classes_list_frame, height=10, width=22, 
                                                font=("Arial", 12),
                                                xscrollcommand=classes_x_scroll.set,
                                                yscrollcommand=classes_y_scroll.set)
        self.current_classes_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Configure scrollbar commands
        classes_y_scroll.config(command=self.current_classes_listbox.yview)
        classes_x_scroll.config(command=self.current_classes_listbox.xview)

        self.current_classes_listbox.bind("<<ListboxSelect>>", self.on_class_selected)
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_selected)

        self.filename_label = tk.Label(self.root, text="", font=("Arial", 15))
        self.filename_label.pack(pady=2)

        self.mode_label = tk.Label(self.root, text="Annotation Mode: OFF", font=("Arial", 12), fg="gray")
        self.mode_label.pack(pady=2)

        self.root.bind('<Left>', lambda event: self.prev_image())
        self.root.bind('<Right>', lambda event: self.next_image())
        self.root.bind('<a>', lambda event: self.prev_image())
        self.root.bind('<d>', lambda event: self.next_image())
        self.root.bind('<Delete>', self.delete_selected_box)
        self.root.bind('<w>', lambda event: self.toggle_annotation_mode())
        self.root.bind('<Control-o>', lambda event: self.open_directory())
        self.root.bind('<Control-s>', lambda event: self.save_annotations())
        self.root.bind('<Control-z>', lambda event: self.undo_annotation())
        self.root.bind('<Control-e>', lambda event: self.change_class_for_selected_box())
        self.root.bind('<Control-a>', self.select_all_boxes)
        self.root.bind('<Control-c>', self.copy_selected_box)
        self.root.bind('<Control-v>', self.paste_copied_box)
        self.root.bind('<Control-Shift-KeyPress-C>', self.copy_selected_box_with_class)
        self.root.bind('<Control-Shift-KeyPress-V>', self.paste_copied_box_with_class)
        self.root.bind('<Control-y>', self.redo_annotation)
     
        self.canvas.bind('<ButtonPress-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_release)
        self.canvas.bind('<Double-Button-1>', self.on_seg_double_click)

        self.canvas.bind('<Button-3>', self.on_canvas_right_click)  # Right click for box selection
        self.root.bind('<Return>', self.on_seg_finish_key)
        self.root.bind('<Escape>', self.on_seg_cancel_key)


    def cycle_draw_mode(self):
        self.draw_mode = 'seg' if self.draw_mode == 'bbox' else 'bbox'
        self.update_mode_ui()

    def cycle_annotation_and_mode(self):
        # W: OFF -> BBOX -> SEG -> OFF
        if not self.class_names:
            messagebox.showwarning("No Classes", "Please load or create classes first.")
            return

        if not self.annotation_mode:
            self.annotation_mode = True
            self.draw_mode = 'bbox'
        else:
            if self.draw_mode == 'bbox':
                self.draw_mode = 'seg'
            else:
                self.annotation_mode = False
                self.draw_mode = 'bbox'
                self.cancel_seg_drawing()

        self.update_mode_ui()

    def update_mode_ui(self):
        if self.annotation_mode:
            if self.draw_mode == 'bbox':
                self.mode_label.config(text="🟢 Annotation Mode: ON (BBOX)", fg="green")
            else:
                self.mode_label.config(text="🟣 Annotation Mode: ON (SEG)", fg="purple")
        else:
            self.mode_label.config(text="⚪ Annotation Mode: OFF", fg="gray")

        self.draw_mode_button.config(text=f"Draw: {'BBOX' if self.draw_mode == 'bbox' else 'SEG'}")

    def cancel_seg_drawing(self):
        for pid in self.seg_point_ids:
            try:
                self.canvas.delete(pid)
            except Exception:
                pass
        self.seg_point_ids.clear()

        for lid in self.seg_segment_ids:
            try:
                self.canvas.delete(lid)
            except Exception:
                pass
        self.seg_segment_ids.clear()

        self.seg_points.clear()

        if self.seg_preview_line_id:
            try:
                self.canvas.delete(self.seg_preview_line_id)
            except Exception:
                pass
        self.seg_preview_line_id = None

        if self.seg_close_preview_id:
            try:
                self.canvas.delete(self.seg_close_preview_id)
            except Exception:
                pass
        self.seg_close_preview_id = None

    def on_seg_add_point(self, event):
        if not (self.image_x <= event.x <= self.image_x + self.display_width and
                self.image_y <= event.y <= self.image_y + self.display_height):
            return

        x = max(self.image_x, min(event.x, self.image_x + self.display_width))
        y = max(self.image_y, min(event.y, self.image_y + self.display_height))
        self.seg_points.append((x, y))

        pid = self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, outline='magenta', fill='magenta')
        self.seg_point_ids.append(pid)

        if len(self.seg_points) >= 2:
            x1, y1 = self.seg_points[-2]
            x2, y2 = self.seg_points[-1]
            lid = self.canvas.create_line(x1, y1, x2, y2, fill='magenta', width=2)
            self.seg_segment_ids.append(lid)
            self.canvas.tag_raise(lid)

        self.canvas.tag_raise(pid)

    def on_seg_preview(self, event):
        if not self.seg_points:
            return

        x = max(self.image_x, min(event.x, self.image_x + self.display_width))
        y = max(self.image_y, min(event.y, self.image_y + self.display_height))
        x1, y1 = self.seg_points[-1]

        if self.seg_preview_line_id:
            self.canvas.coords(self.seg_preview_line_id, x1, y1, x, y)
        else:
            self.seg_preview_line_id = self.canvas.create_line(x1, y1, x, y, fill='magenta', width=1, dash=(3, 2))

        if len(self.seg_points) >= 2:
            fx, fy = self.seg_points[0]
            if self.seg_close_preview_id:
                self.canvas.coords(self.seg_close_preview_id, x, y, fx, fy)
            else:
                self.seg_close_preview_id = self.canvas.create_line(x, y, fx, fy, fill='magenta', width=1, dash=(3, 2))
            self.canvas.tag_raise(self.seg_close_preview_id)

        self.canvas.tag_raise(self.seg_preview_line_id)

    def on_seg_double_click(self, event):
        if not (self.annotation_mode and self.draw_mode == 'seg'):
            return
        self.finish_seg_drawing(event_x=event.x, event_y=event.y)

    def on_seg_finish_key(self, event=None):
        if not (self.annotation_mode and self.draw_mode == 'seg'):
            return
        self.finish_seg_drawing()

    def on_seg_cancel_key(self, event=None):
        if not (self.annotation_mode and self.draw_mode == 'seg'):
            return
        self.cancel_seg_drawing()

    def finish_seg_drawing(self, event_x=None, event_y=None):
        if len(self.seg_points) < 3:
            self.cancel_seg_drawing()
            return

        self.has_unsaved_changes = True

        flat_points = []
        rel_points = []
        for (x, y) in self.seg_points:
            flat_points.extend([x, y])
            rx, ry = self.canvas_to_image_coords(x, y)
            rx = max(0.0, min(1.0, rx))
            ry = max(0.0, min(1.0, ry))
            rel_points.extend([rx, ry])

        poly_id = self.canvas.create_polygon(*flat_points, outline='magenta', fill='', width=2)
        self.seg_poly_ids.append(poly_id)
        self.cancel_seg_drawing()

        self.selected_box_id = poly_id
        self.selected_shape_kind = 'seg'
        self.multi_selected_boxes = [poly_id]

        def assign_seg_class(cls_id):
            self.seg_annotations.append((cls_id, rel_points))
            x0, y0 = flat_points[0], flat_points[1]
            label = self.canvas.create_text(
                x0 + 5, y0 - 20,
                text=self.class_names[cls_id] if cls_id < len(self.class_names) else str(cls_id),
                anchor='nw',
                fill='magenta',
                font=("Arial", 12, "bold")
            )
            self.seg_label_ids.append(label)
            self.update_current_classes_listbox()

        px = event_x if event_x is not None else (self.image_x + 20)
        py = event_y if event_y is not None else (self.image_y + 20)
        self.show_class_selector_popup(assign_seg_class,
                                       x=int(self.root.winfo_rootx() + px),
                                       y=int(self.root.winfo_rooty() + py))


    def copy_labels_to_all_images(self):
        if not self.dataset_path or not self.image_list:
            messagebox.showwarning("No Dataset", "Please open a dataset directory first.")
            return

        # Copy labels from CURRENT image to ALL other images in folder
        src_bbox = list(self.annotations)
        src_seg = list(self.seg_annotations)

        if not src_bbox and not src_seg:
            messagebox.showinfo("No Labels", "Current image has no labels to copy.")
            return

        current_img = self.image_list[self.current_image_index] if self.image_list else ''
        written = 0
        skipped = 0
        for img in self.image_list:
            # Skip current image to avoid overwriting its existing txt
            if img == current_img:
                skipped += 1
                continue

            file_name = pathlib.Path(img).stem + ".txt"
            save_path = pathlib.Path(self.dataset_path) / file_name
            with open(save_path, 'w', encoding='utf-8') as f:
                for ann in src_bbox:
                    f.write(f"{ann[0]} {ann[1]:.6f} {ann[2]:.6f} {ann[3]:.6f} {ann[4]:.6f}\n")
                for cls_id, rel_points in src_seg:
                    pts_str = ' '.join(f"{v:.6f}" for v in rel_points)
                    f.write(f"{cls_id} {pts_str}\n")
            written += 1

        print(f"✅ Copied labels to {written} image(s). Skipped current: {skipped}.")
    def open_directory(self):
        self.dataset_path = filedialog.askdirectory()
        if not self.dataset_path:
            return

        all_files = os.listdir(self.dataset_path)
        self.image_list = [f for f in all_files if f.lower().endswith(('.jpg', '.png'))]
        self.image_list.sort()

        # Update copy target dropdown
        try:
            menu = self.copy_target_menu["menu"]
            menu.delete(0, "end")
            for img in self.image_list:
                menu.add_command(label=img, command=lambda v=img: self.copy_target_var.set(v))
            # Default: next image if possible, else current
            if self.image_list:
                default_idx = min(1, len(self.image_list) - 1)
                self.copy_target_var.set(self.image_list[default_idx])
        except Exception as e:
            print(f"[Copy Target Dropdown Error]: {e}")

        # Load classes.txt automatically if exists
        class_txt_path = os.path.join(self.dataset_path, "classes.txt")
        if os.path.exists(class_txt_path):
            with open(class_txt_path, 'r') as f:
                self.class_names = [line.strip()[:100] for line in f.readlines() if line.strip()]
        else:
            self.class_names = []

        self.image_listbox.delete(0, tk.END)
        for file in self.image_list:
            self.image_listbox.insert(tk.END, file)

        self.current_image_index = 0
        self.load_image()

    def run_training_script(self):
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'YOLOv8_Trainer.py')
        if os.path.exists(script_path):
            try:
                subprocess.Popen([sys.executable, script_path])
                print("[Train] ✅ YOLOv8_Trainer.py launched.")
            except Exception as e:
                print(f"[Train] ❌ Failed to launch training script: {e}")
        else:
            print("[Train] ❌ YOLOv8_Trainer.py not found in the same folder.")

    def load_image(self):
        if not self.image_list:
            return

        self.has_unsaved_changes = False  # Reset unsaved changes flag
        self.current_image_path = os.path.join(self.dataset_path, self.image_list[self.current_image_index])
        pil_image = Image.open(self.current_image_path)

        # Store original dimensions
        self.original_width, self.original_height = pil_image.size
        
        # Calculate display size to maintain aspect ratio
        canvas_width = self.canvas.winfo_width() or 800
        canvas_height = self.canvas.winfo_height() or 600
        
        # Calculate scaling to fit in canvas while preserving aspect ratio
        width_ratio = canvas_width / self.original_width
        height_ratio = canvas_height / self.original_height
        scale = min(width_ratio, height_ratio) * 0.9  # 90% of available space
        
        self.display_width = int(self.original_width * scale)
        self.display_height = int(self.original_height * scale)
        
        # Resize image for display
        display_image = pil_image.resize((self.display_width, self.display_height), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(display_image)

        # Calculate image position to center it
        self.image_x = (canvas_width - self.display_width) // 2
        self.image_y = (canvas_height - self.display_height) // 2

        self.canvas.delete("all")
        
        # Draw border around image area
        self.canvas.create_rectangle(
            self.image_x - 1, self.image_y - 1,
            self.image_x + self.display_width + 1,
            self.image_y + self.display_height + 1,
            outline='white'
        )
        
        # Draw the image
        self.canvas.create_image(
            self.image_x + self.display_width//2,
            self.image_y + self.display_height//2,
            image=self.tk_image
        )

        self.annotations.clear()
        self.rect_ids.clear()
        self.label_ids.clear()
        self.temp_boxes.clear()
        self.seg_annotations.clear()
        self.seg_poly_ids.clear()
        self.seg_label_ids.clear()
        self.cancel_seg_drawing()
        
        # Load annotations if they exist
        txt_file = os.path.splitext(self.image_list[self.current_image_index])[0] + ".txt"
        txt_path = os.path.join(self.dataset_path, txt_file)
        
        if os.path.exists(txt_path):
            with open(txt_path, 'r') as f:
                lines = f.readlines()
            for line in lines:
                parts = line.strip().split()
                if len(parts) == 5:
                    cls_id, cx, cy, w, h = int(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    
                    # Convert YOLO coordinates to canvas coordinates
                    x1, y1, x2, y2 = self.yolo_to_canvas_coords(cx, cy, w, h)
                    
                    # Create rectangle and label
                    rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline='red')
                    self.rect_ids.append(rect)
                    
                    label = self.canvas.create_text(
                        x1 + 5, y1 - 20,
                        text=self.class_names[cls_id] if cls_id < len(self.class_names) else str(cls_id),
                        anchor='nw',
                        fill='red',
                        font=("Arial", 12, "bold")
                    )
                    self.label_ids.append(label)
                    
                    # Store original YOLO coordinates
                    self.annotations.append((cls_id, cx, cy, w, h))

                elif len(parts) > 5 and len(parts[1:]) % 2 == 0:
                    try:
                        cls_id = int(parts[0])
                        coords = [float(x) for x in parts[1:]]
                        canvas_points = []
                        rel_points = []
                        for i in range(0, len(coords), 2):
                            rx, ry = coords[i], coords[i + 1]
                            rel_points.extend([rx, ry])
                            cxp, cyp = self.image_to_canvas_coords(rx, ry)
                            canvas_points.extend([cxp, cyp])

                        poly = self.canvas.create_polygon(*canvas_points, outline='magenta', fill='', width=2)
                        self.seg_poly_ids.append(poly)
                        self.seg_annotations.append((cls_id, rel_points))

                        lx, ly = canvas_points[0], canvas_points[1]
                        label = self.canvas.create_text(lx + 5, ly - 20, text=(self.class_names[cls_id] if cls_id < len(self.class_names) else str(cls_id)), anchor='nw', fill='magenta', font=('Arial', 12, 'bold'))
                        self.seg_label_ids.append(label)
                    except Exception as e:
                        print(f'[Load Seg Error]: {e}')

        # Update UI elements
        self.filename_label.config(text=f"Current Image: {self.image_list[self.current_image_index]}")
        self.image_listbox.selection_clear(0, tk.END)
        self.image_listbox.selection_set(self.current_image_index)
        self.image_listbox.activate(self.current_image_index)
        self.root.title(f"YOLOv8 Label Tool - {self.image_list[self.current_image_index]}")
        
        # Update current classes listbox
        self.update_current_classes_listbox()
        
        # Ensure labels are visible
        self.root.after(100, self.ensure_all_labels_visible)

    def update_current_classes_listbox(self):
        """Update the listbox showing classes in current image"""
        self.current_classes_listbox.delete(0, tk.END)
        
        # Get unique class IDs from annotations
        unique_classes = set()
        for ann in self.annotations:
            cls_id = ann[0]
            if cls_id < len(self.class_names):
                unique_classes.add(cls_id)
        for ann in self.seg_annotations:
            cls_id = ann[0]
            if cls_id < len(self.class_names):
                unique_classes.add(cls_id)
        
        # Sort by class ID and add to listbox
        for cls_id in sorted(unique_classes):
            class_name = self.class_names[cls_id]
            count = sum(1 for ann in self.annotations if ann[0] == cls_id) + sum(1 for ann in self.seg_annotations if ann[0] == cls_id)
            self.current_classes_listbox.insert(tk.END, f"{class_name} ({count})")

    def on_image_selected(self, event):
        selected = self.image_listbox.curselection()
        if selected and selected[0] != self.current_image_index:
            if not self.check_unsaved_changes():
                # Revert selection if user cancels
                self.image_listbox.selection_clear(0, tk.END)
                self.image_listbox.selection_set(self.current_image_index)
                return
            self.current_image_index = selected[0]
            self.load_image()

    def next_image(self):
        if self.image_list and self.current_image_index < len(self.image_list) - 1:
            if not self.check_unsaved_changes():
                return
            self.current_image_index += 1
            self.load_image()

    def prev_image(self):
        if self.image_list and self.current_image_index > 0:
            if not self.check_unsaved_changes():
                return
            self.current_image_index -= 1
            self.load_image()

    def toggle_annotation_mode(self):
        if not self.class_names:
            messagebox.showwarning("No Classes", "Please load or create classes first.")
            return
        self.annotation_mode = not self.annotation_mode
        if not self.annotation_mode:
            self.cancel_seg_drawing()
        self.update_mode_ui()

    def on_mouse_down(self, event):
        if self.annotation_mode and self.draw_mode == 'bbox':
            # Check if click is within image boundaries
            if (self.image_x <= event.x <= self.image_x + self.display_width and 
                self.image_y <= event.y <= self.image_y + self.display_height):
                # Store the original click coordinates
                self.start_x = max(self.image_x, min(event.x, self.image_x + self.display_width))
                self.start_y = max(self.image_y, min(event.y, self.image_y + self.display_height))
                self.rect = self.canvas.create_rectangle(
                    self.start_x, self.start_y, 
                    self.start_x, self.start_y, 
                    outline='yellow'
                )
                self.temp_boxes.append(self.rect)
        elif self.annotation_mode and self.draw_mode == 'seg':
            self.on_seg_add_point(event)
        elif self.selected_box_id:
            if self.selected_box_id in self.multi_selected_boxes:
                self.dragging = True
                self.drag_offset_x = event.x
                self.drag_offset_y = event.y
                self.drag_start_coords = {
                    box_id: self.canvas.coords(box_id)
                    for box_id in self.multi_selected_boxes
                    if self.canvas.type(box_id) in ("rectangle", "polygon")
                }


    def on_mouse_drag(self, event):
        if self.annotation_mode and self.draw_mode == 'bbox' and self.rect:
            current_x = max(self.image_x, min(event.x, self.image_x + self.display_width))
            current_y = max(self.image_y, min(event.y, self.image_y + self.display_height))
            self.canvas.coords(self.rect,
                self.start_x, self.start_y,
                current_x, current_y
            )
        elif self.annotation_mode and self.draw_mode == 'seg':
            self.on_seg_preview(event)
        elif self.dragging and self.selected_box_id and self.multi_selected_boxes:
            dx = event.x - self.drag_offset_x
            dy = event.y - self.drag_offset_y

            # boundary check for all selected shapes
            can_move = True
            for box_id in self.multi_selected_boxes:
                coords = self.canvas.coords(box_id)
                t = self.canvas.type(box_id)
                if t == 'rectangle' and len(coords) == 4:
                    new_x1 = coords[0] + dx
                    new_y1 = coords[1] + dy
                    new_x2 = coords[2] + dx
                    new_y2 = coords[3] + dy
                elif t == 'polygon' and len(coords) >= 6:
                    xs = coords[0::2]
                    ys = coords[1::2]
                    new_x1 = min(xs) + dx
                    new_y1 = min(ys) + dy
                    new_x2 = max(xs) + dx
                    new_y2 = max(ys) + dy
                else:
                    continue

                if (new_x1 < self.image_x or new_x2 > self.image_x + self.display_width or
                    new_y1 < self.image_y or new_y2 > self.image_y + self.display_height):
                    can_move = False
                    break

            if can_move:
                for box_id in self.multi_selected_boxes:
                    self.canvas.move(box_id, dx, dy)

                    if box_id in self.rect_ids:
                        idx = self.rect_ids.index(box_id)
                        if idx < len(self.label_ids):
                            self.canvas.move(self.label_ids[idx], dx, dy)

                    if box_id in self.seg_poly_ids:
                        idx = self.seg_poly_ids.index(box_id)
                        if idx < len(self.seg_label_ids):
                            self.canvas.move(self.seg_label_ids[idx], dx, dy)

                self.drag_offset_x = event.x
                self.drag_offset_y = event.y

    def on_mouse_release(self, event):
        if self.annotation_mode and self.draw_mode == 'bbox' and self.rect:
            x1, y1, x2, y2 = self.canvas.coords(self.rect)

            if abs(x2 - x1) < 5 or abs(y2 - y1) < 5:
                self.canvas.delete(self.rect)
                if self.rect in self.temp_boxes:
                    self.temp_boxes.remove(self.rect)
                self.rect = None
                return

            self.has_unsaved_changes = True
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            self.canvas.coords(self.rect, x1, y1, x2, y2)

            current_rect = self.rect
            self.selected_box_id = current_rect
            self.rect = None

            self.ensure_all_labels_visible()
            self.root.after(100, lambda: self.change_class_for_selected_box())

        elif self.dragging and self.selected_box_id and self.multi_selected_boxes:
            moved = []

            for box_id in self.multi_selected_boxes:
                before = self.drag_start_coords.get(box_id) if self.drag_start_coords else None
                after = self.canvas.coords(box_id)

                if before and after and before != after:
                    moved.append({'box_id': box_id, 'from': before, 'to': after})

                    # update bbox annotation
                    if box_id in self.rect_ids and len(after) == 4:
                        try:
                            idx = self.rect_ids.index(box_id)
                            x1, y1, x2, y2 = after
                            cx, cy, w, h = self.convert_coords_to_yolo(x1, y1, x2, y2)
                            cls_id = self.annotations[idx][0]
                            self.annotations[idx] = (cls_id, cx, cy, w, h)

                            if idx < len(self.label_ids):
                                label_id = self.label_ids[idx]
                                self.canvas.coords(label_id, x1 + 5, y1 - 20)
                                self.canvas.tag_raise(label_id)
                        except Exception as e:
                            print(f"[Move Update Error]: {e}")

                    # update seg annotation
                    if box_id in self.seg_poly_ids and len(after) >= 6:
                        try:
                            sidx = self.seg_poly_ids.index(box_id)
                            rel_points = []
                            for i in range(0, len(after), 2):
                                rx, ry = self.canvas_to_image_coords(after[i], after[i + 1])
                                rx = max(0.0, min(1.0, rx))
                                ry = max(0.0, min(1.0, ry))
                                rel_points.extend([rx, ry])

                            cls_id = self.seg_annotations[sidx][0]
                            self.seg_annotations[sidx] = (cls_id, rel_points)

                            if sidx < len(self.seg_label_ids):
                                self.canvas.coords(self.seg_label_ids[sidx], after[0] + 5, after[1] - 20)
                                self.canvas.tag_raise(self.seg_label_ids[sidx])
                        except Exception as e:
                            print(f"[Move SEG Update Error]: {e}")

            if moved:
                self.undo_stack.append({'action': 'move_group', 'boxes': moved})
                self.redo_stack.clear()

            self.drag_start_coords = None
            self.dragging = False
            self.ensure_all_labels_visible()

    def open_class_selector_for_rect(
self, x1, y1, x2, y2, rect_obj):
        if not self.class_names:
            messagebox.showwarning("No Classes", "Please load or create classes first.")
            self.canvas.delete(rect_obj)
            if rect_obj in self.temp_boxes:
                self.temp_boxes.remove(rect_obj)
            return

        # Calculate popup position relative to the main window
        popup_w, popup_h = 250, 300
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        canvas_x = self.canvas.winfo_x()
        canvas_y = self.canvas.winfo_y()
        
        # Position near the drawn box but ensure it's visible
        x_pos = root_x + canvas_x + min(x2, self.canvas.winfo_width() - popup_w)
        y_pos = root_y + canvas_y + min(y2, self.canvas.winfo_height() - popup_h)

        popup = tk.Toplevel(self.root)
        popup.title("Select Class")
        popup.geometry(f"{popup_w}x{popup_h}+{x_pos}+{y_pos}")
        popup.transient(self.root)  # Make it transient to main window
        popup.grab_set()  # Make it modal
        popup.focus_force()  # Force focus

        # Add search functionality
        search_var = tk.StringVar()
        search_entry = tk.Entry(popup, textvariable=search_var, font=("Arial", 14))
        search_entry.pack(fill=tk.X, padx=5, pady=5)
        search_entry.focus_set()

        listbox = tk.Listbox(popup, font=("Arial", 14))
        listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Populate listbox
        for i, cls in enumerate(self.class_names):
            listbox.insert(tk.END, f"{i}: {cls}")

        def update_list(*args):
            search_term = search_var.get().lower()
            listbox.delete(0, tk.END)
            for i, cls in enumerate(self.class_names):
                if search_term in cls.lower():
                    listbox.insert(tk.END, f"{i}: {cls}")

        search_var.trace_add("write", update_list)

        def assign_class(event=None):
            selection = listbox.curselection()
            if not selection:
                self.canvas.delete(rect_obj)
                if rect_obj in self.temp_boxes:
                    self.temp_boxes.remove(rect_obj)
                popup.destroy()
                return

            # Get selected class
            text = listbox.get(selection[0])
            cls_id = int(text.split(":")[0])

            # Calculate YOLO format coordinates
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            box_width = (x2 - x1) / canvas_w
            box_height = (y2 - y1) / canvas_h
            center_x = (x1 + x2) / 2 / canvas_w
            center_y = (y1 + y2) / 2 / canvas_h

            # Save annotation
            self.annotations.append((cls_id, center_x, center_y, box_width, box_height))
            self.rect_ids.append(rect_obj)
            if rect_obj in self.temp_boxes:
                self.temp_boxes.remove(rect_obj)

            # Create label
            label = self.canvas.create_text(
                x1 + 5, y1 - 20,
                text=self.class_names[cls_id],
                anchor='nw',
                fill='yellow',
                font=("Arial", 12, "bold")
            )
            self.label_ids.append(label)

            # Add to undo stack
            self.undo_stack.append({
                'action': 'draw',
                'coords': (x1, y1, x2, y2),
                'type': 'classified',
                'class': cls_id,
                'box_id': rect_obj,
                'label_id': label
            })
            self.redo_stack.clear()

            # Update box appearance
            self.canvas.itemconfig(rect_obj, outline='red')
            
            popup.destroy()

        # Bind events
        listbox.bind('<Return>', assign_class)
        listbox.bind('<Double-Button-1>', assign_class)
        listbox.bind('<ButtonRelease-1>', assign_class)
        popup.bind('<Return>', assign_class)
        popup.bind('<Escape>', lambda e: popup.destroy())

        # Handle window close
        def on_popup_close():
            if rect_obj in self.temp_boxes:
                self.temp_boxes.remove(rect_obj)
            self.canvas.delete(rect_obj)
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_popup_close)

    def show_class_selector_popup(self, callback, x=100, y=100):
        popup_w, popup_h = 250, 300
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x_pos = min(max(0, x), screen_w - popup_w)
        y_pos = min(max(0, y), screen_h - popup_h - 90)

        popup = tk.Toplevel(self.root)
        popup.title("Select Class")
        popup.geometry(f"{popup_w}x{popup_h}+{x_pos}+{y_pos}")
        popup.grab_set()

        font_config = ("Arial", 14)

        search_var = tk.StringVar()
        search_entry = tk.Entry(popup, textvariable=search_var, font=font_config)
        search_entry.pack(fill=tk.X, padx=5, pady=5)

        listbox = tk.Listbox(popup, font=font_config)
        listbox.pack(fill=tk.BOTH, expand=True)

        def update_list(*args):
            search_term = search_var.get().lower()
            listbox.delete(0, tk.END)
            for i, cls in enumerate(self.class_names):
                if search_term in cls.lower():
                    listbox.insert(tk.END, f"{i}: {cls}")

        search_var.trace_add("write", update_list)
        update_list()

        def select_and_close(event):
            selection = listbox.curselection()
            if selection:
                text = listbox.get(selection[0])
                cls_id = int(text.split(":")[0])
                callback(cls_id)
            popup.destroy()

        listbox.bind('<ButtonRelease-1>', select_and_close)
        search_entry.focus_set()

    def handle_mouse_release(self, event):
        if self.annotation_mode:
            self.on_mouse_release(event)         # handles box drawing + class selection
        elif self.dragging:
            self.on_mouse_release(event)           # handles drag-to-move

    def save_annotations(self, silent=False):
        if not self.dataset_path or not self.image_list:
            return False
        file_name = os.path.splitext(self.image_list[self.current_image_index])[0] + ".txt"
        save_path = os.path.join(self.dataset_path, file_name)
        with open(save_path, 'w') as f:
            for ann in self.annotations:
                f.write(f"{ann[0]} {ann[1]:.6f} {ann[2]:.6f} {ann[3]:.6f} {ann[4]:.6f}\n")
            for cls_id, rel_points in self.seg_annotations:
                pts_str = ' '.join(f'{v:.6f}' for v in rel_points)
                f.write(f'{cls_id} {pts_str}\n')
        if not silent:
            print(f"✅ Annotations saved to {file_name}")
        self.has_unsaved_changes = False
        return True

    def check_unsaved_changes(self):
        if self.has_unsaved_changes:
            response = messagebox.askyesnocancel("Unsaved Changes", 
                "You have unsaved changes. Would you like to save before proceeding?")
            if response is None:  # Cancel
                return False
            if response:  # Yes
                self.save_annotations(silent=True)
            # If No, proceed without saving
            self.has_unsaved_changes = False
            return True
        return True

    def new_class_file(self):
        if not self.dataset_path:
            messagebox.showwarning("Warning", "Please open a dataset directory first.")
            return
        class_editor = tk.Toplevel(self.root)
        class_editor.title("New Classes")
        class_editor.geometry("400x500")
        text_area = tk.Text(class_editor)
        text_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        def save_new_classes():
            content = text_area.get("1.0", tk.END).strip()
            lines = [line[:100] for line in content.splitlines() if line.strip()]
            with open(os.path.join(self.dataset_path, "classes.txt"), 'w') as f:
                for line in lines:
                    f.write(line + '\n')
            messagebox.showinfo("Saved", "classes.txt saved successfully.")
            class_editor.destroy()
        tk.Button(class_editor, text="Save", command=save_new_classes).pack(side=tk.BOTTOM, pady=5)

    def select_class_file(self):
        if not self.dataset_path:
            messagebox.showwarning("Warning", "Please open a dataset directory first.")
            return
        selected_file = filedialog.askopenfilename(initialdir=self.dataset_path, filetypes=[("Text Files", "*.txt")])
        if selected_file:
            self.class_file = selected_file
            with open(self.class_file, 'r') as f:
                self.class_names = [line.strip()[:100] for line in f.readlines() if line.strip()]
            messagebox.showinfo("Class Loaded", f"Loaded {len(self.class_names)} classes.")

    def edit_class_file(self):
        if not self.class_file:
            messagebox.showwarning("Warning", "Please select a class file first.")
            return
        editor = tk.Toplevel(self.root)
        editor.title("Edit Classes")
        editor.geometry("400x500")
        text_area = tk.Text(editor)
        text_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        with open(self.class_file, 'r') as f:
            text_area.insert(tk.END, f.read())
        def save_edited_classes():
            content = text_area.get("1.0", tk.END).strip()
            lines = [line[:100] for line in content.splitlines() if line.strip()]
            with open(self.class_file, 'w') as f:
                for line in lines:
                    f.write(line + '\n')
            messagebox.showinfo("Saved", "Classes updated successfully.")
            editor.destroy()
        tk.Button(editor, text="Save", command=save_edited_classes).pack(side=tk.BOTTOM, pady=5)

    def on_canvas_right_click(self, event):
        clicked_box = None
        all_boxes = self.rect_ids + self.temp_boxes + self.seg_poly_ids

        for rect_id in reversed(all_boxes):
            coords = self.canvas.coords(rect_id)
            if len(coords) != 4:
                continue
            x1, y1, x2, y2 = coords
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                clicked_box = rect_id
                break

        if clicked_box is None:
            self.clear_selection()
        else:
            shift_held = event.state & 0x0001
            self.select_box(clicked_box, multi=shift_held)

    def clear_selection(self):
        # Deselect single
        if self.selected_box_id:
            if self.selected_box_id in self.rect_ids:
                self.canvas.itemconfig(self.selected_box_id, dash=(), outline='red')
            elif self.selected_box_id in self.temp_boxes:
                self.canvas.itemconfig(self.selected_box_id, dash=(), outline='yellow')
        self.selected_box_id = None
        self.selected_label_id = None

        # Deselect multi
        for box_id in self.multi_selected_boxes:
            if box_id in self.rect_ids:
                self.canvas.itemconfig(box_id, dash=(), outline='red')
            elif box_id in self.temp_boxes:
                self.canvas.itemconfig(box_id, dash=(), outline='yellow')
        self.multi_selected_boxes.clear()


    def change_class_for_selected_box(self):
        if self.selected_box_id is None:
            messagebox.showinfo("No Box Selected", "Please right-click to select a box first.")
            return

        self.has_unsaved_changes = True  # Mark as having unsaved changes
        is_temp = self.selected_box_id in self.temp_boxes
        if not is_temp and self.selected_box_id not in self.rect_ids:
            return

        x1, y1, x2, y2 = self.canvas.coords(self.selected_box_id)
        popup_w, popup_h = 450, 300
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x_pos = int(min(max(0, self.root.winfo_rootx() + x1), screen_w - popup_w))
        y_pos = int(min(max(0, self.root.winfo_rooty() + y1), screen_h - popup_h - 90))

        popup = tk.Toplevel(self.root)
        popup.title("Change or Add Class")
        popup.geometry(f"{popup_w}x{popup_h}+{x_pos}+{y_pos}")
        popup.grab_set()
        popup.focus_force()

        font_config = ("Arial", 14)

        entry = tk.Entry(popup, font=font_config)
        entry.pack(fill=tk.X, padx=5, pady=3)
        entry.focus()

        listbox = tk.Listbox(popup, font=font_config)
        listbox.pack(fill=tk.BOTH, expand=True)

        # Initial fill
        for i, cls in enumerate(self.class_names):
            listbox.insert(tk.END, f"{i}: {cls}")

        def update_filter(*args):
            query = entry.get().lower()
            listbox.delete(0, tk.END)
            for i, cls in enumerate(self.class_names):
                if query in cls.lower():
                    listbox.insert(tk.END, f"{i}: {cls}")

        entry.bind("<KeyRelease>", update_filter)

        def apply_class(event=None):
            selection = listbox.curselection()
            if not selection:
                popup.destroy()
                return

            list_value = listbox.get(selection[0])
            cls_id = int(list_value.split(":")[0])

            # Calculate YOLO coordinates
            cx, cy, w, h = self.convert_coords_to_yolo(x1, y1, x2, y2)

            if is_temp:
                # New classification on unclassified box
                self.annotations.append((cls_id, cx, cy, w, h))
                self.rect_ids.append(self.selected_box_id)
                self.temp_boxes.remove(self.selected_box_id)

                # Create new label for this box
                label = self.canvas.create_text(
                    x1 + 5, y1 - 20,
                    text=self.class_names[cls_id],
                    anchor='nw',
                    fill='yellow',
                    font=("Arial", 12, "bold")
                )
                self.label_ids.append(label)
                self.selected_label_id = label
            else:
                # Update existing box's class
                index = self.rect_ids.index(self.selected_box_id)
                self.annotations[index] = (cls_id, cx, cy, w, h)

                # Update existing label
                if index < len(self.label_ids):
                    label_id = self.label_ids[index]
                    if label_id:
                        self.canvas.itemconfig(label_id,
                            text=self.class_names[cls_id],
                            state='normal'
                        )
                        self.canvas.coords(label_id, x1 + 5, y1 - 20)
                        self.canvas.tag_raise(label_id)

            # Update box appearance
            self.canvas.itemconfig(self.selected_box_id, outline='red')

            # Add to undo stack
            self.undo_stack.append({
                'action': 'draw' if is_temp else 'change_class',
                'coords': (x1, y1, x2, y2),
                'type': 'classified',
                'class': cls_id,
                'box_id': self.selected_box_id,
                'label_id': self.selected_label_id
            })
            self.redo_stack.clear()

            # Update classes listbox
            self.update_current_classes_listbox()

            popup.destroy()

        # Bind events
        listbox.bind('<Return>', apply_class)
        listbox.bind('<Double-Button-1>', apply_class)
        listbox.bind('<ButtonRelease-1>', apply_class)
        popup.bind('<Return>', apply_class)
        popup.bind('<Escape>', lambda e: popup.destroy())

        def on_popup_close():
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_popup_close)

    def copy_selected_box(self, event=None):
        self.clipboard_boxes.clear()
        seen = set()
        valid_count = 0

        for box_id in self.multi_selected_boxes:
            if box_id in seen:
                continue
            seen.add(box_id)

            if self.canvas.type(box_id) != "rectangle":
                continue
                
            coords = self.canvas.coords(box_id)
            if len(coords) != 4:
                continue
                
            x1, y1, x2, y2 = coords
            
            # Convert to relative coordinates (0-1 range)
            rel_x1, rel_y1 = self.canvas_to_image_coords(x1, y1)
            rel_x2, rel_y2 = self.canvas_to_image_coords(x2, y2)
            
            # Store relative coordinates
            self.clipboard_boxes.append({
                'rel_x1': rel_x1,
                'rel_y1': rel_y1,
                'rel_x2': rel_x2,
                'rel_y2': rel_y2
            })
            valid_count += 1

        if valid_count == 0:
            print("[Copy] ❌ No valid box copied.")
        else:
            print(f"[Copy] ✅ {valid_count} box(es) copied with relative position.")

    def copy_selected_box_with_class(self, event=None):
        self.clipboard_boxes.clear()
        seen = set()
        valid_count = 0

        for box_id in self.multi_selected_boxes:
            if box_id in seen or box_id not in self.rect_ids:
                continue
            seen.add(box_id)

            if self.canvas.type(box_id) != "rectangle":
                continue
                
            coords = self.canvas.coords(box_id)
            if len(coords) != 4:
                continue
                
            x1, y1, x2, y2 = coords
            
            # Convert to relative coordinates (0-1 range)
            rel_x1, rel_y1 = self.canvas_to_image_coords(x1, y1)
            rel_x2, rel_y2 = self.canvas_to_image_coords(x2, y2)
            
            # Get the class information
            idx = self.rect_ids.index(box_id)
            if idx < len(self.annotations):
                cls_id = self.annotations[idx][0]
                
                # Store relative coordinates and class info
                self.clipboard_boxes.append({
                    'rel_x1': rel_x1,
                    'rel_y1': rel_y1,
                    'rel_x2': rel_x2,
                    'rel_y2': rel_y2,
                    'class_id': cls_id,
                    'class_name': self.class_names[cls_id]
                })
                valid_count += 1

        if valid_count == 0:
            print("[Copy with Class] ❌ No valid classified box copied.")
        else:
            print(f"[Copy with Class] ✅ {valid_count} classified box(es) copied with relative position and class.")

    def paste_copied_box(self, event=None):
        if not self.clipboard_boxes or 'rel_x1' not in self.clipboard_boxes[0]:
            print("[Paste] ❌ Clipboard is empty or invalid.")
            return

        self.clear_selection()
        self.redo_stack.clear()
        self.has_unsaved_changes = True  # Mark as having unsaved changes

        new_boxes = []
        pasted_box_ids = []

        for box_info in self.clipboard_boxes:
            # Convert relative coordinates to canvas coordinates
            x1, y1 = self.image_to_canvas_coords(box_info['rel_x1'], box_info['rel_y1'])
            x2, y2 = self.image_to_canvas_coords(box_info['rel_x2'], box_info['rel_y2'])

            # Create new box at the calculated position
            box_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline='yellow')
            self.temp_boxes.append(box_id)
            pasted_box_ids.append(box_id)

            new_boxes.append({
                'coords': (x1, y1, x2, y2),
                'type': 'unclassified',
                'class': None,
                'box_id': box_id
            })

        # Add all boxes to undo stack
        self.undo_stack.extend(new_boxes)

        # Select all newly pasted boxes
        self.multi_selected_boxes = pasted_box_ids
        self.selected_box_id = pasted_box_ids[-1] if pasted_box_ids else None

        # Highlight all pasted boxes as selected
        for box_id in pasted_box_ids:
            self.canvas.itemconfig(box_id, dash=(4, 2), outline='orange')

        print(f"[Paste] ✅ {len(new_boxes)} box(es) pasted at relative positions and selected.")

    def paste_copied_box_with_class(self, event=None):
        if not self.clipboard_boxes or 'rel_x1' not in self.clipboard_boxes[0] or 'class_id' not in self.clipboard_boxes[0]:
            print("[Paste with Class] ❌ No classified boxes in clipboard.")
            return

        self.clear_selection()
        self.redo_stack.clear()
        self.has_unsaved_changes = True  # Mark as having unsaved changes

        new_boxes = []
        pasted_box_ids = []

        for box_info in self.clipboard_boxes:
            # Convert relative coordinates to canvas coordinates
            x1, y1 = self.image_to_canvas_coords(box_info['rel_x1'], box_info['rel_y1'])
            x2, y2 = self.image_to_canvas_coords(box_info['rel_x2'], box_info['rel_y2'])
            cls_id = box_info['class_id']

            # Create new box at the calculated position
            box_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline='red')
            self.rect_ids.append(box_id)
            pasted_box_ids.append(box_id)

            # Create label
            label = self.canvas.create_text(
                x1 + 5, y1 - 20,
                text=box_info['class_name'],
                anchor='nw',
                fill='yellow',
                font=("Arial", 12, "bold")
            )
            self.label_ids.append(label)

            # Calculate YOLO format coordinates
            cx, cy, w, h = self.convert_coords_to_yolo(x1, y1, x2, y2)

            # Add to annotations
            self.annotations.append((cls_id, cx, cy, w, h))

            new_boxes.append({
                'action': 'draw',
                'coords': (x1, y1, x2, y2),
                'type': 'classified',
                'class': cls_id,
                'box_id': box_id,
                'label_id': label
            })

        # Add all boxes to undo stack
        self.undo_stack.extend(new_boxes)

        # Select all newly pasted boxes
        self.multi_selected_boxes = pasted_box_ids
        self.selected_box_id = pasted_box_ids[-1] if pasted_box_ids else None

        # Highlight all pasted boxes as selected
        for box_id in pasted_box_ids:
            self.canvas.itemconfig(box_id, dash=(4, 2), outline='orange')

        print(f"[Paste with Class] ✅ {len(new_boxes)} box(es) pasted with their classes.")


    def select_box(self, box_id, multi=False):
        item_type = self.canvas.type(box_id)
        if item_type not in ("rectangle", "polygon"):
            return

        # turn off annotation mode when selecting
        if self.annotation_mode:
            self.annotation_mode = False
            self.cancel_seg_drawing()
            self.update_mode_ui()

        if not multi:
            self.clear_selection()

        if box_id in self.multi_selected_boxes:
            if multi:
                self.multi_selected_boxes.remove(box_id)
                if box_id in self.rect_ids:
                    self.canvas.itemconfig(box_id, dash=(), outline='red')
                elif box_id in self.temp_boxes:
                    self.canvas.itemconfig(box_id, dash=(), outline='yellow')
                elif box_id in self.seg_poly_ids:
                    self.canvas.itemconfig(box_id, dash=(), outline='magenta', width=2)
            else:
                self.multi_selected_boxes = [box_id]
        else:
            self.multi_selected_boxes.append(box_id)

        # highlight all selected
        for bid in self.multi_selected_boxes:
            if bid in self.seg_poly_ids:
                self.canvas.itemconfig(bid, dash=(4, 2), outline='orange', width=3)
            else:
                self.canvas.itemconfig(bid, dash=(4, 2), outline='orange')

        self.selected_box_id = box_id

        # track label id
        if box_id in self.rect_ids:
            idx = self.rect_ids.index(box_id)
            self.selected_label_id = self.label_ids[idx] if idx < len(self.label_ids) else None
        elif box_id in self.seg_poly_ids:
            idx = self.seg_poly_ids.index(box_id)
            self.selected_label_id = self.seg_label_ids[idx] if idx < len(self.seg_label_ids) else None
        else:
            self.selected_label_id = None

    def select_all_boxes(self, event=None):
        self.clear_selection()
        all_boxes = self.rect_ids + self.temp_boxes + self.seg_poly_ids

        for box_id in all_boxes:
            self.multi_selected_boxes.append(box_id)
            if box_id in self.seg_poly_ids:
                self.canvas.itemconfig(box_id, dash=(4, 2), outline='orange', width=3)
            else:
                self.canvas.itemconfig(box_id, dash=(4, 2), outline='orange')

        if all_boxes:
            self.selected_box_id = all_boxes[-1]
            if self.selected_box_id in self.rect_ids:
                idx = self.rect_ids.index(self.selected_box_id)
                self.selected_label_id = self.label_ids[idx] if idx < len(self.label_ids) else None
            elif self.selected_box_id in self.seg_poly_ids:
                idx = self.seg_poly_ids.index(self.selected_box_id)
                self.selected_label_id = self.seg_label_ids[idx] if idx < len(self.seg_label_ids) else None
            else:
                self.selected_label_id = None

            if self.annotation_mode:
                self.annotation_mode = False
                self.cancel_seg_drawing()
                self.update_mode_ui()

        print(f"[Select All] ✅ {len(all_boxes)} shape(s) selected.")

    def delete_selected_box(self, event=None):
        if not self.multi_selected_boxes:
            return

        self.has_unsaved_changes = True
        deleted_boxes = []

        for box_id in self.multi_selected_boxes[:]:
            coords = self.canvas.coords(box_id)
            if not coords:
                continue

            box_info = {
                'coords': coords,
                'box_id': box_id
            }

            if box_id in self.rect_ids:
                idx = self.rect_ids.index(box_id)
                box_info['type'] = 'classified'
                box_info['class'] = self.annotations[idx][0]

                if idx < len(self.label_ids):
                    self.canvas.delete(self.label_ids[idx])
                    del self.label_ids[idx]

                del self.annotations[idx]
                del self.rect_ids[idx]

            elif box_id in self.temp_boxes:
                box_info['type'] = 'unclassified'
                box_info['class'] = None
                self.temp_boxes.remove(box_id)

            elif box_id in self.seg_poly_ids:
                idx = self.seg_poly_ids.index(box_id)
                box_info['type'] = 'seg'
                box_info['class'] = self.seg_annotations[idx][0] if idx < len(self.seg_annotations) else None

                if idx < len(self.seg_label_ids):
                    self.canvas.delete(self.seg_label_ids[idx])
                    del self.seg_label_ids[idx]

                if idx < len(self.seg_annotations):
                    del self.seg_annotations[idx]
                del self.seg_poly_ids[idx]

            self.canvas.delete(box_id)
            deleted_boxes.append(box_info)

        if deleted_boxes:
            self.undo_stack.append({
                'action': 'delete_group',
                'boxes': deleted_boxes
            })
            self.redo_stack.clear()
            self.update_current_classes_listbox()

        self.multi_selected_boxes.clear()
        self.selected_box_id = None
        self.selected_label_id = None

        print(f"[Delete] ✅ {len(deleted_boxes)} shape(s) deleted.")

    def undo_annotation(self, event=None):

        if not self.undo_stack:
            print("[Undo] ❌ Nothing to undo.")
            return

        box = self.undo_stack.pop()
        self.redo_stack.append(box)

        # 🔄 Undo group move
        if box.get("action") == "move_group":
            for entry in box["boxes"]:
                box_id = entry["box_id"]
                from_coords = entry["from"]
                to_coords = entry["to"]
                
                # Only proceed if the box still exists
                if self.canvas.type(box_id) == "rectangle":
                    self.canvas.coords(box_id, *from_coords)
                    
                    if box_id in self.rect_ids:
                        idx = self.rect_ids.index(box_id)
                        # Update YOLO coordinates
                        cx, cy, w, h = self.convert_coords_to_yolo(*from_coords)
                        cls_id = self.annotations[idx][0]
                        self.annotations[idx] = (cls_id, cx, cy, w, h)
                        
                        # Move the label if it exists
                        if idx < len(self.label_ids):
                            label_id = self.label_ids[idx]
                            dx = from_coords[0] - to_coords[0]
                            dy = from_coords[1] - to_coords[1]
                            self.canvas.move(label_id, dx, dy)
                            
                            # Ensure the label is visible
                            self.canvas.itemconfig(label_id, state='normal')
                            
                            # Update label position to be above the box
                            self.canvas.coords(label_id, 
                                from_coords[0] + 5,  # x position
                                from_coords[1] - 20  # y position
                            )
                            
                            # Ensure box is visible and properly colored
                            self.canvas.itemconfig(box_id, 
                                state='normal',
                                outline='red' if box_id in self.rect_ids else 'yellow'
                            )
            
            print(f"[Undo] ↩️ Moved group of {len(box['boxes'])} boxes back.")
            return

        # 🔄 Undo delete group
        if box.get("action") == "delete_group":
            restored = []
            for entry in box["boxes"]:
                x1, y1, x2, y2 = entry["coords"]
                box_type = entry["type"]
                cls_id = entry["class"]

                # Create new box with same coordinates
                new_box_id = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    outline="red" if box_type == "classified" else "yellow"
                )

                if box_type == "classified":
                    self.rect_ids.append(new_box_id)
                    self.annotations.append((cls_id, *self.convert_coords_to_yolo(x1, y1, x2, y2)))
                    
                    # Create new label
                    label = self.canvas.create_text(
                        x1 + 5, y1 - 20,
                        text=self.class_names[cls_id],
                        anchor='nw',
                        fill='yellow',
                        font=("Arial", 12, "bold")
                    )
                    self.label_ids.append(label)
                    entry["label_id"] = label
                else:
                    self.temp_boxes.append(new_box_id)

                entry["box_id"] = new_box_id
                restored.append(entry)

            # Update redo stack with new IDs
            self.redo_stack[-1]["boxes"] = restored
            
            # Update classes listbox
            self.update_current_classes_listbox()
            
            print(f"[Undo] ✅ Restored group of {len(restored)} deleted boxes.")
            return

        # 🔄 Undo single box draw/delete
        if box.get("action") == "draw":
            box_id = box["box_id"]
            if box["type"] == "classified":
                if box_id in self.rect_ids:
                    idx = self.rect_ids.index(box_id)
                    del self.annotations[idx]
                    del self.rect_ids[idx]
                    if idx < len(self.label_ids):
                        self.canvas.delete(self.label_ids[idx])
                        del self.label_ids[idx]
                self.canvas.delete(box_id)
            else:  # unclassified
                if box_id in self.temp_boxes:
                    self.temp_boxes.remove(box_id)
                self.canvas.delete(box_id)
                
            # Update classes listbox
            self.update_current_classes_listbox()
            
            print("[Undo] ✅ Removed drawn box.")
            return

        print("[Undo] ❓ Unknown action type.")

    def redo_annotation(self, event=None):
        if not self.redo_stack:
            print("[Redo] ❌ Nothing to redo.")
            return

        box = self.redo_stack.pop()

        # 🔁 Redo single box move
        if box.get("action") == "move":
            self.canvas.coords(box["box_id"], *box["to"])
            if box["box_id"] in self.rect_ids:
                idx = self.rect_ids.index(box["box_id"])
                cx, cy, w, h = self.convert_coords_to_yolo(*box["to"])
                cls_id = self.annotations[idx][0]
                self.annotations[idx] = (cls_id, cx, cy, w, h)
                self.canvas.move(self.label_ids[idx],
                                box["to"][0] - box["from"][0],
                                box["to"][1] - box["from"][1])
            self.undo_stack.append(box)
            print("[Redo] 🔁 Box moved forward to new position.")
            return

        # 🔁 Redo group move
        if box.get("action") == "move_group":
            for entry in box["boxes"]:
                box_id = entry["box_id"]
                from_coords = entry["from"]
                to_coords = entry["to"]
                self.canvas.coords(box_id, *to_coords)
                if box_id in self.rect_ids:
                    idx = self.rect_ids.index(box_id)
                    cx, cy, w, h = self.convert_coords_to_yolo(*to_coords)
                    cls_id = self.annotations[idx][0]
                    self.annotations[idx] = (cls_id, cx, cy, w, h)
                    self.canvas.move(
                        self.label_ids[idx],
                        to_coords[0] - from_coords[0],
                        to_coords[1] - from_coords[1]
                    )
            self.undo_stack.append(box)
            print(f"[Redo] 🔁 Group of {len(box['boxes'])} boxes moved forward.")
            return

        if box.get("action") == "delete_group":
            for entry in box["boxes"]:
                box_id = entry.get("box_id")
                label_id = entry.get("label_id")

                if box_id:
                    self.canvas.delete(box_id)
                if label_id:
                    self.canvas.delete(label_id)

                if entry["type"] == "classified":
                    if box_id in self.rect_ids:
                        idx = self.rect_ids.index(box_id)
                        del self.rect_ids[idx]
                        del self.annotations[idx]
                        del self.label_ids[idx]
                elif entry["type"] == "unclassified":
                    if box_id in self.temp_boxes:
                        self.temp_boxes.remove(box_id)

            self.undo_stack.append(box)
            
            # Update classes listbox
            self.update_current_classes_listbox()
            
            print(f"[Redo] 🔁 Re-deleted group of {len(box['boxes'])} boxes.")
            return

        if box.get("action") == "draw":
            x1, y1, x2, y2 = box["coords"]
            box_type = box["type"]
            cls_id = box.get("class")

            box_id = self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="red" if box_type == "classified" else "yellow"
            )

            if box_type == "classified":
                self.rect_ids.append(box_id)
                self.annotations.append((cls_id, *self.convert_coords_to_yolo(x1, y1, x2, y2)))
                label = self.canvas.create_text(
                    x1 + 5, y1 - 20,
                    text=self.class_names[cls_id],
                    anchor='nw',
                    fill='yellow',
                    font=("Arial", 12, "bold")
                )
                self.label_ids.append(label)
                box["label_id"] = label
            else:
                self.temp_boxes.append(box_id)

            box["box_id"] = box_id
            box["coords"] = (x1, y1, x2, y2)
            self.undo_stack.append(box)
            
            # Update classes listbox
            self.update_current_classes_listbox()
            
            print("[Redo] ✅ Re-drew one box.")
            return

        print("[Redo] ❓ Unknown redo action.")

    def convert_coords_to_yolo(self, x1, y1, x2, y2):
        """Convert canvas coordinates to normalized YOLO coordinates (0-1 range)"""
        # Convert from canvas to image-relative coordinates
        rel_x1 = (x1 - self.image_x) / self.display_width
        rel_y1 = (y1 - self.image_y) / self.display_height
        rel_x2 = (x2 - self.image_x) / self.display_width
        rel_y2 = (y2 - self.image_y) / self.display_height
        
        # Calculate center point and dimensions
        cx = (rel_x1 + rel_x2) / 2
        cy = (rel_y1 + rel_y2) / 2
        w = abs(rel_x2 - rel_x1)
        h = abs(rel_y2 - rel_y1)
        
        # Clamp values to 0-1 range
        cx = max(0, min(1, cx))
        cy = max(0, min(1, cy))
        w = max(0, min(1, w))
        h = max(0, min(1, h))
        
        return cx, cy, w, h

    def yolo_to_canvas_coords(self, cx, cy, w, h):
        """Convert YOLO coordinates to canvas coordinates"""
        # Calculate box corners in relative coordinates
        x1_rel = cx - (w / 2)
        y1_rel = cy - (h / 2)
        x2_rel = cx + (w / 2)
        y2_rel = cy + (h / 2)
        
        # Convert to canvas coordinates
        x1 = self.image_x + (x1_rel * self.display_width)
        y1 = self.image_y + (y1_rel * self.display_height)
        x2 = self.image_x + (x2_rel * self.display_width)
        y2 = self.image_y + (y2_rel * self.display_height)
        
        return x1, y1, x2, y2

    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """Convert canvas coordinates to image-relative coordinates"""
        rel_x = (canvas_x - self.image_x) / self.display_width
        rel_y = (canvas_y - self.image_y) / self.display_height
        return rel_x, rel_y

    def image_to_canvas_coords(self, rel_x, rel_y):
        """Convert image-relative coordinates to canvas coordinates"""
        canvas_x = self.image_x + (rel_x * self.display_width)
        canvas_y = self.image_y + (rel_y * self.display_height)
        return canvas_x, canvas_y

    def ensure_all_labels_visible(self):
        """Helper method to ensure all labels are visible"""
        for idx, (box_id, label_id) in enumerate(zip(self.rect_ids, self.label_ids)):
            if label_id and box_id:
                try:
                    # Get the box's current coordinatesda
                    box_coords = self.canvas.coords(box_id)
                    if box_coords and len(box_coords) == 4:
                        x1, y1 = box_coords[0], box_coords[1]
                        
                        # Get the class name for this box
                        cls_id = self.annotations[idx][0]
                        class_name = self.class_names[cls_id]
                        
                        # Update label position and text
                        self.canvas.coords(label_id, x1 + 5, y1 - 20)
                        self.canvas.itemconfig(label_id, 
                            state='normal',
                            text=class_name,
                            fill='yellow',
                            font=("Arial", 12, "bold")
                        )
                        self.canvas.tag_raise(label_id)
                except Exception as e:
                    print(f"Label visibility error for box {idx}: {e}")


    def on_class_selected(self, event):
        """Handle class selection from the current classes listbox"""
        selection = self.current_classes_listbox.curselection()
        if not selection:
            return

        # turn off drawing when selecting
        if self.annotation_mode:
            self.annotation_mode = False
            self.cancel_seg_drawing()
            self.update_mode_ui()

        self.clear_selection()

        selected_text = self.current_classes_listbox.get(selection[0])
        selected_class = selected_text.split(" (")[0]

        try:
            cls_id = self.class_names.index(selected_class)
        except ValueError:
            return

        # bbox
        for i, ann in enumerate(self.annotations):
            if ann[0] == cls_id and i < len(self.rect_ids):
                box_id = self.rect_ids[i]
                self.multi_selected_boxes.append(box_id)
                self.canvas.itemconfig(box_id, dash=(4, 2), outline='orange')

        # seg
        for i, ann in enumerate(self.seg_annotations):
            if ann[0] == cls_id and i < len(self.seg_poly_ids):
                poly_id = self.seg_poly_ids[i]
                self.multi_selected_boxes.append(poly_id)
                self.canvas.itemconfig(poly_id, dash=(4, 2), outline='orange', width=3)

        if self.multi_selected_boxes:
            self.selected_box_id = self.multi_selected_boxes[-1]

        print(f"[Class Select] ✅ Selected {len(self.multi_selected_boxes)} shape(s) of class '{selected_class}'")

    def show_help(self):
        help_window = tk.Toplevel(self.root)
        help_window.title("YOLO Label Tool - Help Guide")
        help_window.geometry("800x600")
        
        # Create text widget
        text_widget = tk.Text(help_window, wrap=tk.WORD, padx=10, pady=10, font=("Arial", 11))
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        # Add scrollbar
        scrollbar = tk.Scrollbar(help_window, command=text_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.config(yscrollcommand=scrollbar.set)
        
        # Make text widget read-only
        text_widget.config(state=tk.NORMAL)
        
        help_text = """YOLO Label Tool - User Guide

Basic Workflow:
1. Open a directory containing your images
2. Create or select a classes.txt file
3. Start annotating images
4. Save your work
5. Navigate between images

Buttons and Commands:
------------------
Top Toolbar Buttons:
• Open Dir - Open a directory containing images to label
• New Class - Create a new classes.txt file
• Select Class File - Choose an existing classes.txt file
• Edit Class - Modify the current classes.txt file
• Change Class - Change the class of selected box(es)
• < Prev - Go to previous image
• Next > - Go to next image
• Undo - Undo last action
• Redo - Redo last undone action
• Save - Save annotations for current image
• Select All - Select all boxes in current image
• Help - Show this help guide

Keyboard Shortcuts:
------------------
Navigation:
• Left Arrow or 'A' - Previous image
• Right Arrow or 'D' - Next image
• 'W' - Toggle annotation mode

Box Operations:
• Delete - Delete selected box(es)
• Ctrl + A - Select all boxes
• Ctrl + Z - Undo
• Ctrl + Y - Redo
• Ctrl + S - Save annotations
• Ctrl + E - Change class of selected box

Copy/Paste Operations:
• Ctrl + C - Copy selected box(es)
• Ctrl + V - Paste copied box(es)
• Ctrl + Shift + C - Copy box(es) with class
• Ctrl + Shift + V - Paste box(es) with class

Mouse Controls:
------------------
Drawing:
• Toggle annotation mode ('W' key)
• Left-click and drag to draw a box
• Release to finish drawing and select class

Selection:
• Right-click on box to select it
• Right-click + Shift to select multiple boxes
• Right-click empty area to deselect all

Moving:
• Left-click and drag selected box(es) to move
• Boxes cannot be moved outside image boundaries

Tips and Best Practices:
------------------
1. Save frequently (Ctrl + S)
2. Use keyboard shortcuts for faster workflow
3. Toggle annotation mode when not drawing boxes
4. Use multi-select for batch operations
5. Copy/paste with class to duplicate similar objects

File Formats:
------------------
• Images: Supports .jpg and .png files
• Annotations: YOLO format .txt files
• Classes: Plain text file, one class per line

YOLO Format:
------------------
Each annotation line: <class_id> <x_center> <y_center> <width> <height>
• All values are normalized (0-1)
• class_id starts from 0
• Coordinates are relative to image size"""

        text_widget.insert(tk.END, help_text)
        text_widget.config(state=tk.DISABLED)  # Make read-only
        
        # Add close button at bottom
        tk.Button(help_window, text="Close", command=help_window.destroy).pack(pady=10)

if __name__ == '__main__':
    root = tk.Tk()
    app = YOLOLabelTool(root)
    root.mainloop()

    