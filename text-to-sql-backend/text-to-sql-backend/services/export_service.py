import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
from typing import Dict, Any, List
from datetime import datetime
import os

class ExportService:
    """Service for exporting data to various formats"""
    
    def __init__(self):
        self.export_dir = "/tmp/exports"
        os.makedirs(self.export_dir, exist_ok=True)
    
    def export_to_csv(self, data: List[Dict[str, Any]], filename: str) -> str:
        """Export data to CSV file"""
        try:
            df = pd.DataFrame(data)
            filepath = os.path.join(self.export_dir, f"{filename}.csv")
            df.to_csv(filepath, index=False)
            return filepath
        except Exception as e:
            raise Exception(f"CSV export failed: {str(e)}")
    
    def export_to_excel(self, data: List[Dict[str, Any]], filename: str, 
                       sheet_name: str = "Sheet1") -> str:
        """Export data to Excel file"""
        try:
            df = pd.DataFrame(data)
            filepath = os.path.join(self.export_dir, f"{filename}.xlsx")
            
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                # Get workbook and worksheet
                workbook = writer.book
                worksheet = writer.sheets[sheet_name]
                
                # Auto-adjust column widths
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            return filepath
        except Exception as e:
            raise Exception(f"Excel export failed: {str(e)}")
    
    def export_to_pdf(self, data: List[Dict[str, Any]], filename: str, 
                     title: str = "Data Export") -> str:
        """Export data to PDF file"""
        try:
            filepath = os.path.join(self.export_dir, f"{filename}.pdf")
            
            # Create PDF document
            doc = SimpleDocTemplate(
                filepath,
                pagesize=landscape(A4) if len(data) > 0 and len(data[0]) > 5 else letter,
                topMargin=0.5*inch,
                bottomMargin=0.5*inch
            )
            
            # Container for PDF elements
            elements = []
            
            # Styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor=colors.HexColor('#1e40af'),
                spaceAfter=12,
                alignment=1  # Center
            )
            
            # Add title
            elements.append(Paragraph(title, title_style))
            elements.append(Spacer(1, 0.2*inch))
            
            # Add metadata
            metadata_style = styles['Normal']
            metadata = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Records: {len(data)}"
            elements.append(Paragraph(metadata, metadata_style))
            elements.append(Spacer(1, 0.2*inch))
            
            if data:
                # Prepare table data
                df = pd.DataFrame(data)
                
                # Limit columns if too many
                if len(df.columns) > 10:
                    df = df.iloc[:, :10]
                
                # Convert to table data
                table_data = [df.columns.tolist()] + df.values.tolist()
                
                # Limit rows for PDF
                if len(table_data) > 51:  # 1 header + 50 data rows
                    table_data = table_data[:51]
                    elements.append(Paragraph(
                        f"Note: Showing first 50 of {len(data)} records",
                        styles['Italic']
                    ))
                    elements.append(Spacer(1, 0.1*inch))
                
                # Create table
                table = Table(table_data)
                
                # Style the table
                table.setStyle(TableStyle([
                    # Header style
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    
                    # Data style
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                
                elements.append(table)
            else:
                elements.append(Paragraph("No data available", styles['Normal']))
            
            # Build PDF
            doc.build(elements)
            
            return filepath
        except Exception as e:
            raise Exception(f"PDF export failed: {str(e)}")
    
    def export_query_results(self, data: List[Dict[str, Any]], 
                           export_format: str, 
                           table_name: str = "query_results") -> str:
        """Export query results in specified format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{table_name}_{timestamp}"
        
        if export_format.lower() == "csv":
            return self.export_to_csv(data, filename)
        elif export_format.lower() == "excel":
            return self.export_to_excel(data, filename, sheet_name=table_name)
        elif export_format.lower() == "pdf":
            return self.export_to_pdf(data, filename, title=f"Table: {table_name}")
        else:
            raise ValueError(f"Unsupported export format: {export_format}")

# Singleton instance
export_service = ExportService()
