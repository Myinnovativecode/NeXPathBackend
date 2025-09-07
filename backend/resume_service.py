from fastapi import APIRouter, HTTPException, Depends, Form, Query
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from postgres_models import Resume
from postgres_client import SessionLocal
from datetime import datetime
import os
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
import logging

logger = logging.getLogger(__name__)
resume_router = APIRouter(prefix="/resumes", tags=["Resumes"])


# Enhanced Data Models
class PersonalInfo(BaseModel):
    name: str
    email: str
    phone: str
    address: Optional[str] = None
    linkedin: Optional[str] = None


class WorkExperience(BaseModel):
    job_title: str
    company: str
    location: Optional[str] = None
    start_date: str
    end_date: str
    responsibilities: List[str] = []


class Education(BaseModel):
    degree: str
    institution: str
    location: Optional[str] = None
    graduation_year: str
    gpa: Optional[str] = None


class Project(BaseModel):
    title: str
    description: str
    technologies: Optional[List[str]] = []
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class Certification(BaseModel):
    name: str
    issuing_organization: str
    date_obtained: str


class ResumeData(BaseModel):
    user_id: str
    personal_info: PersonalInfo
    professional_summary: Optional[str] = None
    skills: List[str] = []
    work_experience: List[WorkExperience] = []
    education: List[Education] = []
    projects: Optional[List[Project]] = []
    certifications: Optional[List[Certification]] = []
    template: str = "professional"  # "professional" or "modern"


def get_resume_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def generate_professional_template(resume_id: int, data: ResumeData) -> str:
    """Generate the professional template similar to Ishika Rawat's resume"""
    os.makedirs("static/resumes", exist_ok=True)
    filename = f"resume_{resume_id}_professional.pdf"
    filepath = f"static/resumes/{filename}"

    # Use a more precise page size and margins to match professional layout
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        rightMargin=50,  # Tighter margins
        leftMargin=50,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    # Enhanced styles to match the professional template
    name_style = ParagraphStyle(
        'Name',
        parent=styles['Heading1'],
        fontSize=16,
        fontName='Helvetica-Bold',
        textColor=colors.black,
        alignment=TA_LEFT,
        spaceAfter=2,  # Less space after name
    )

    contact_style = ParagraphStyle(
        'Contact',
        parent=styles['Normal'],
        fontSize=9,  # Smaller font for contact details
        alignment=TA_LEFT,
        spaceAfter=12,
        leading=12  # Line height
    )

    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=10,
        fontName='Helvetica-Bold',
        textColor=colors.black,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=4,
        # No border - the first resume uses uppercase text without borders
    )

    subsection_style = ParagraphStyle(
        'SubsectionHeading',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica-Bold',
        textColor=colors.black,
        spaceBefore=6,
        spaceAfter=1,
        leading=12
    )

    content_style = ParagraphStyle(
        'Content',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_LEFT,
        spaceAfter=2,
        leading=12  # Tighter line height for content
    )

    bullet_style = ParagraphStyle(
        'BulletPoint',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_LEFT,
        leftIndent=10,  # Indentation for bullet points
        spaceAfter=1,
        leading=12
    )

    story = []

    # Header - Name in UPPERCASE with proper styling
    story.append(Paragraph(data.personal_info.name.upper(), name_style))

    # Contact info on a single line with separators
    contact_parts = []
    if data.personal_info.linkedin:
        contact_parts.append(f"LinkedIn: {data.personal_info.linkedin}")
    if data.personal_info.address:
        contact_parts.append(data.personal_info.address)
    contact_parts.append(f"Mobile: {data.personal_info.phone}")
    contact_parts.append(f"Email: {data.personal_info.email}")

    contact_text = " | ".join(contact_parts)
    story.append(Paragraph(contact_text, contact_style))

    # Add a divider line
    story.append(Spacer(1, 6))

    # EDUCATION
    story.append(Paragraph("EDUCATION", section_heading_style))

    if data.education:
        for edu in data.education:
            # Institution name and location on same line
            institution_line = f"<b>{edu.institution}</b>"
            if edu.location:
                institution_line += f" - {edu.location}"
            story.append(Paragraph(institution_line, content_style))

            # Degree and GPA
            degree_line = f"{edu.degree}"
            if edu.gpa:
                degree_line += f" - GPA: {edu.gpa}"
            story.append(Paragraph(degree_line, content_style))

            # Graduation year
            story.append(Paragraph(f"Graduation: {edu.graduation_year}", content_style))
            story.append(Spacer(1, 6))

    # SKILLS SUMMARY
    if data.skills:
        story.append(Paragraph("SKILLS SUMMARY", section_heading_style))

        # Categorize skills similar to the sample resume
        skill_categories = {
            "Languages": [],
            "Frameworks": [],
            "Tools": [],
            "Platforms": [],
            "Other": []
        }

        # Simple categorization logic - could be improved with AI or better mapping
        for skill in data.skills:
            skill_lower = skill.lower()
            if skill_lower in ['python', 'java', 'javascript', 'c++', 'c#', 'sql', 'r', 'ruby', 'php', 'go']:
                skill_categories["Languages"].append(skill)
            elif skill_lower in ['react', 'angular', 'vue', 'django', 'flask', 'spring', 'node.js', 'express', '.net']:
                skill_categories["Frameworks"].append(skill)
            elif skill_lower in ['git', 'docker', 'kubernetes', 'jenkins', 'jira', 'postman', 'vscode']:
                skill_categories["Tools"].append(skill)
            elif skill_lower in ['aws', 'azure', 'gcp', 'linux', 'windows', 'macos', 'ios', 'android']:
                skill_categories["Platforms"].append(skill)
            else:
                skill_categories["Other"].append(skill)

        # Format skills by category
        for category, skills in skill_categories.items():
            if skills:
                story.append(Paragraph(f"<b>• {category}:</b> {', '.join(skills)}", content_style))

        story.append(Spacer(1, 6))

    # WORK EXPERIENCE
    story.append(Paragraph("WORK EXPERIENCE", section_heading_style))

    if data.work_experience:
        for exp in data.work_experience:
            # Company, location, and dates on one line
            company_line = f"<b>{exp.company}</b>"
            if exp.location:
                company_line += f" | {exp.location}"
            company_line += f" | {exp.start_date} - {exp.end_date}"
            story.append(Paragraph(company_line, content_style))

            # Job title in italics
            story.append(Paragraph(f"<i>{exp.job_title}</i>", content_style))

            # Responsibilities as bullet points
            for resp in exp.responsibilities:
                if resp.strip():  # Skip empty responsibilities
                    story.append(Paragraph(f"• {resp}", bullet_style))

            story.append(Spacer(1, 8))

    # PROJECTS
    if data.projects and any(p.title for p in data.projects):
        story.append(Paragraph("PROJECTS", section_heading_style))

        for project in data.projects:
            if not project.title:
                continue

            # Project title and dates
            project_line = f"<b>{project.title}</b>"
            if project.start_date and project.end_date:
                project_line += f" | {project.start_date} - {project.end_date}"
            story.append(Paragraph(project_line, content_style))

            # Project description
            if project.description:
                story.append(Paragraph(project.description, content_style))

            # Technologies used
            if project.technologies and len(project.technologies) > 0:
                tech_text = f"<b>Technologies:</b> {', '.join(project.technologies)}"
                story.append(Paragraph(tech_text, content_style))

            story.append(Spacer(1, 6))

    # CERTIFICATIONS
    if data.certifications and any(c.name for c in data.certifications):
        story.append(Paragraph("CERTIFICATIONS", section_heading_style))

        for cert in data.certifications:
            if not cert.name:
                continue

            cert_line = f"<b>{cert.name}</b> | {cert.issuing_organization} | {cert.date_obtained}"
            story.append(Paragraph(cert_line, content_style))

            story.append(Spacer(1, 3))

    # Build the PDF
    doc.build(story)

    return f"http://localhost:8000/static/resumes/{filename}"


def generate_modern_template(resume_id: int, data: ResumeData) -> str:
    """Generate the modern template with clean design"""
    os.makedirs("static/resumes", exist_ok=True)
    filename = f"resume_{resume_id}_modern.pdf"
    filepath = f"static/resumes/{filename}"

    doc = SimpleDocTemplate(filepath, pagesize=A4, rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=72)

    styles = getSampleStyleSheet()

    # Modern template styles
    name_style = ParagraphStyle(
        'Name',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=6,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#2C3E50'),
        fontName='Helvetica-Bold'
    )

    contact_style = ParagraphStyle(
        'Contact',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=20,
        alignment=TA_CENTER
    )

    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=8,
        spaceBefore=16,
        textColor=colors.HexColor('#2C3E50'),
        fontName='Helvetica-Bold',
        borderWidth=2,
        borderPadding=4,
        borderColor=colors.HexColor('#3498DB'),
        backColor=colors.HexColor('#ECF0F1')
    )

    content_style = ParagraphStyle(
        'Content',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        leftIndent=0
    )

    story = []

    # Header
    story.append(Paragraph(data.personal_info.name, name_style))

    contact_info = [
        data.personal_info.email,
        data.personal_info.phone
    ]
    if data.personal_info.linkedin:
        contact_info.append(f"LinkedIn: {data.personal_info.linkedin}")
    if data.personal_info.address:
        contact_info.append(data.personal_info.address)

    story.append(Paragraph(" | ".join(contact_info), contact_style))

    # Professional Summary
    if data.professional_summary:
        story.append(Paragraph("PROFESSIONAL SUMMARY", section_heading_style))
        story.append(Paragraph(data.professional_summary, content_style))

    # Rest of the sections follow similar pattern...
    # (Skills, Experience, Education, Projects, Certifications)
    # Similar to professional template but with modern styling

    doc.build(story)
    return f"http://localhost:8000/static/resumes/{filename}"


# Template selection endpoint
@resume_router.get("/templates")
def get_resume_templates():
    """Get available resume templates"""
    return {
        "templates": [
            {
                "id": "professional",
                "name": "Professional Template",
                "description": "Clean, traditional format perfect for corporate roles",
                "preview_url": "https://example.com/professional-preview.png"
            },
            {
                "id": "modern",
                "name": "Modern Template",
                "description": "Contemporary design with color accents and modern layout",
                "preview_url": "https://www.jobseeker.com/d/OfJtiJ2DqGca6ZJsXbmxQ/view"
            }
        ]
    }


# Replace the create_resume function with this:
@resume_router.post("/")
def create_resume(resume_data: ResumeData, db: Session = Depends(get_resume_db)):
    try:
        # Store in database with proper column names
        db_resume = Resume(
            user_id=resume_data.user_id,
            resume_data=resume_data.dict(),
            file_name=f"{resume_data.personal_info.name.replace(' ', '_')}_Resume_{resume_data.template}.pdf",
            created_at=datetime.utcnow(),  # Use created_at instead of timestamp
            template_used=resume_data.template
        )
        db.add(db_resume)
        db.commit()
        db.refresh(db_resume)

        # Generate resume based on template
        if resume_data.template == "professional":
            download_url = generate_professional_template(db_resume.id, resume_data)
        elif resume_data.template == "modern":
            download_url = generate_modern_template(db_resume.id, resume_data)
        else:
            download_url = generate_professional_template(db_resume.id, resume_data)

        # Update with download URL
        db_resume.download_url = download_url
        db.commit()

        return {
            "success": True,
            "resume_id": db_resume.id,
            "download_url": download_url,
            "template_used": resume_data.template,
            "message": f"Professional resume generated successfully!"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating resume: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create resume: {str(e)}")


# Keep your existing endpoints (delete, rename, etc.)

@resume_router.get("/{resume_id}")
def get_resume(resume_id: int, db: Session = Depends(get_resume_db)):
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume

@resume_router.post("/start_resume_builder/")
async def start_resume_builder(user_id: str):
    return {
        "response": "Let's build your professional resume. Please fill out the form that will appear.",
        "action": "open_resume_form",
        "user_id": user_id
    }


@resume_router.delete("/{resume_id}")
def delete_resume(
        resume_id: int,
        user_id: str,
        db: Session = Depends(get_resume_db)
):
    """Delete a resume by ID"""
    try:
        resume = db.query(Resume).filter(
            Resume.id == resume_id,
            Resume.user_id == user_id
        ).first()

        if not resume:
            raise HTTPException(
                status_code=404,
                detail="Resume not found or does not belong to this user"
            )

        # Delete the physical file if it exists
        if resume.download_url:
            try:
                file_path = resume.download_url.split("/")[-1]
                full_path = os.path.join("static", "resumes", file_path)
                if os.path.exists(full_path):
                    os.remove(full_path)
                    logger.info(f"Deleted resume file: {full_path}")
            except Exception as e:
                logger.error(f"Error deleting resume file: {str(e)}")

        # Delete from database
        db.delete(resume)
        db.commit()

        logger.info(f"Successfully deleted resume {resume_id} for user {user_id}")
        return {"success": True, "message": "Resume deleted successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting resume {resume_id} for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete resume: {str(e)}")


# In resume_service.py

@resume_router.patch("/{resume_id}/rename")
def rename_resume(
        resume_id: int,
        user_id: str,
        new_name: str = Form(...),
        db: Session = Depends(get_resume_db)
):
    """Rename a resume by updating the dedicated file_name column."""
    try:
        resume = db.query(Resume).filter(
            Resume.id == resume_id,
            Resume.user_id == user_id
        ).first()

        if not resume:
            raise HTTPException(
                status_code=404,
                detail="Resume not found or does not belong to this user"
            )

        # --- THIS IS THE FIX ---
        # Update the dedicated 'file_name' column directly, not the JSON blob.
        resume.file_name = new_name
        resume.updated_at = datetime.utcnow() # Also update the timestamp

        # Commit the change to the database
        db.commit()

        logger.info(f"Successfully renamed resume {resume_id} to '{new_name}' for user {user_id}")
        return {"success": True, "message": "Resume renamed successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error renaming resume {resume_id} for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to rename resume: {str(e)}")
