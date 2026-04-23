"""CSV/PDF export and JSON user-data persistence (Tk dialogs)."""

import csv
import json
import os
from tkinter import filedialog, messagebox

from fpdf import FPDF

from .constants import user_data_file
from .plotting import draw_heatmap


def export_csv(results, project_info):
    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
    )
    if not file_path:
        return
    with open(file_path, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Project Info"])
        for key, value in project_info.items():
            writer.writerow([key, value])
        writer.writerow([])
        writer.writerow(results[0].keys())
        for res in results:
            writer.writerow(res.values())
    messagebox.showinfo("Success", "CSV exported successfully!")


def export_pdf(results, project_info, length, width):
    file_path = filedialog.asksaveasfilename(
        defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")]
    )
    if not file_path:
        return

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=False)
    bg_path = "background.png"

    def add_page_with_bg():
        pdf.add_page()
        pdf.image(bg_path, x=0, y=0, w=210, h=297)

    add_page_with_bg()
    pdf.set_font("Arial", size=16)
    pdf.cell(200, 50, "Lighting Design Report", ln=True, align="C")
    pdf.ln(10)
    pdf.set_xy(10, 60)
    pdf.set_font("Arial", size=12)
    for label, value in project_info.items():
        pdf.cell(200, 10, f"{label}: {value}", ln=True)

    for res in results:
        add_page_with_bg()
        pdf.set_font("Arial", size=11)
        pdf.set_xy(10, 50)
        for key, val in res.items():
            pdf.cell(0, 10, f"{key}: {val}", ln=True)

        num_x = int(res["Fixtures"] ** 0.5)
        num_y = res["Fixtures"] // num_x
        heatmap_path = draw_heatmap(length, width, num_x, num_y)
        pdf.image(heatmap_path, x=30, y=160, w=100)

    add_page_with_bg()
    pdf.set_font("Arial", size=12)
    pdf.set_xy(20, 60)
    pdf.multi_cell(
        0,
        10,
        "To avoid electrical instability issues, always use drivers with built-in protections:\n"
        "- Over voltage protection\n"
        "- Over current protection",
    )

    pdf.output(file_path)
    messagebox.showinfo("Success", "PDF exported successfully!")


def save_user_data(project_info, results):
    all_data = load_all_user_data()
    all_data.append({"project_info": project_info, "results": results})
    with open(user_data_file, "w") as f:
        json.dump(all_data, f, indent=4)


def load_all_user_data():
    if os.path.exists(user_data_file):
        with open(user_data_file, "r") as f:
            return json.load(f)
    return []


def export_all_users_to_csv():
    all_data = load_all_user_data()
    if not all_data:
        messagebox.showinfo("No Data", "No user data to export.")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
    )
    if not file_path:
        return

    with open(file_path, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "Project Name",
                "Client Name",
                "Client Number",
                "Company Name",
                "Luminaire",
                "Power (W)",
                "Efficacy (lm/W)",
                "Fixtures",
                "Spacing X (m)",
                "Spacing Y (m)",
                "Average Lux",
                "Uniformity",
                "Total Power (W)",
                "Beam Angle (°)",
            ]
        )
        for data in all_data:
            proj = data["project_info"]
            for res in data["results"]:
                writer.writerow(
                    [
                        proj.get("Project Name", ""),
                        proj.get("Client Name", ""),
                        proj.get("Client Number", ""),
                        proj.get("Company Name", ""),
                        res.get("Luminaire", ""),
                        res.get("Power (W)", ""),
                        res.get("Efficacy (lm/W)", ""),
                        res.get("Fixtures", ""),
                        res.get("Spacing X (m)", ""),
                        res.get("Spacing Y (m)", ""),
                        res.get("Average Lux", ""),
                        res.get("Uniformity", ""),
                        res.get("Total Power (W)", ""),
                        res.get("Beam Angle (°)", ""),
                    ]
                )
    messagebox.showinfo("Success", "All user data exported to CSV successfully!")
