"""Optional Tkinter desktop UI."""

import tkinter as tk
from tkinter import ttk, messagebox

from .calculate import calculate_lighting
from .constants import define_places
from .export_io import (
    export_all_users_to_csv,
    export_csv,
    export_pdf,
    save_user_data,
)
from . import state


def run_gui():
    def on_calculate():
        try:
            place = place_var.get()
            sides = [float(side_vars[i].get()) for i in range(4)]
            height = float(height_var.get())
            project_info = {label: entries[label].get() for label in labels}
            results, length, width, _meta = calculate_lighting(place, sides, height)
            state.results_global.clear()
            state.results_global.extend(results)
            state.project_info_global.clear()
            state.project_info_global.update(project_info)
            result_box.delete(1.0, tk.END)
            for res in results:
                result_box.insert(tk.END, f"{res}\n\n")
            save_user_data(project_info, results)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_export_pdf():
        if state.results_global:
            sides = [float(side_vars[i].get()) for i in range(4)]
            length = max(sides[0], sides[2])
            width = max(sides[1], sides[3])
            export_pdf(state.results_global, state.project_info_global, length, width)

    def on_export_csv():
        if state.results_global:
            export_csv(state.results_global, state.project_info_global)

    root = tk.Tk()
    root.title("Lighting Design App")

    labels = ["Project Name", "Client Name", "Client Number", "Company Name"]
    entries = {}
    for i, label in enumerate(labels):
        tk.Label(root, text=label).grid(row=i, column=0, sticky="w")
        entry = tk.Entry(root)
        entry.grid(row=i, column=1)
        entries[label] = entry

    tk.Label(root, text="Place").grid(row=4, column=0, sticky="w")
    place_var = ttk.Combobox(root, values=list(define_places.keys()))
    place_var.grid(row=4, column=1)

    side_labels = ["Side A (m)", "Side B (m)", "Side C (m)", "Side D (m)"]
    side_vars = []
    for i, label in enumerate(side_labels):
        tk.Label(root, text=label).grid(row=5 + i, column=0, sticky="w")
        var = tk.Entry(root)
        var.grid(row=5 + i, column=1)
        side_vars.append(var)

    tk.Label(root, text="Height (m)").grid(row=9, column=0, sticky="w")
    height_var = tk.Entry(root)
    height_var.grid(row=9, column=1)

    tk.Button(root, text="Calculate", command=on_calculate).grid(
        row=10, column=0, columnspan=2, pady=5
    )
    tk.Button(root, text="Export to PDF", command=on_export_pdf).grid(
        row=11, column=0, columnspan=2, pady=5
    )
    tk.Button(root, text="Export to CSV", command=on_export_csv).grid(
        row=12, column=0, columnspan=2, pady=5
    )
    tk.Button(root, text="Export All Users to CSV", command=export_all_users_to_csv).grid(
        row=13, column=0, columnspan=2, pady=5
    )

    result_box = tk.Text(root, height=20, width=70)
    result_box.grid(row=0, column=2, rowspan=13, padx=10)

    root.mainloop()
