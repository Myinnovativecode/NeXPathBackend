# resume_utils.py

import os
import pdfkit
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = "."

def generate_pdf(data: dict, pdf_filename: str) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("resume_template.html")

    html_content = template.render(data)
    output_path = f"resumes/{pdf_filename}"

    # Ensure the folder exists
    os.makedirs("resumes", exist_ok=True)

    pdfkit.from_string(html_content, output_path)
    return output_path
