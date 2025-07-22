"""
Result exporters for different output formats (CSV, JSON, Excel).
"""

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from urllib.parse import urlparse

class ResultExporter:
    """Handles exporting crawl results to various formats."""

    def __init__(self, config):
        self.config = config

    async def export_results(self, contacts: List[Dict], source_url: str) -> str:
        """Export results in the specified format."""
        try:
            # Generate output filename if not specified
            output_file = self._generate_filename(source_url)
            
            # Export based on format
            if self.config.output_format == 'csv':
                output_path = await self._export_csv(contacts, output_file)
            elif self.config.output_format == 'json':
                output_path = await self._export_json(contacts, output_file)
            elif self.config.output_format == 'excel':
                output_path = await self._export_excel(contacts, output_file)
            else:
                raise ValueError(f"Unsupported output format: {self.config.output_format}")
            
            logging.info(f"Results exported to: {output_path}")
            return output_path
        
        except Exception as e:
            logging.error(f"Error exporting results: {e}")
            raise

    def _generate_filename(self, source_url: str) -> str:
        """Generate a filename based on the source URL and timestamp."""
        if self.config.output_file:
            return self.config.output_file
        
        # Extract domain from URL
        try:
            domain = urlparse(source_url).netloc
            domain = domain.replace('www.', '').replace('.', '_')
        except Exception:
            domain = "unknown"
        
        # Add timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Generate filename
        filename = f"contacts_{domain}_{timestamp}"
        return filename

    async def _export_csv(self, contacts: List[Dict], filename: str) -> str:
        """Export contacts to CSV format."""
        output_path = Path(self.config.output_dir) / f"{filename}.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not contacts:
            logging.warning("No contacts to export")
            return str(output_path)
        
        # Define CSV columns
        columns = [
            'email', 'name', 'title', 'company', 'phone',
            'source_url', 'extraction_method', 'confidence',
            'validation_score', 'context'
        ]
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            
            for contact in contacts:
                # Clean the contact data for CSV
                cleaned_contact = self._clean_contact_for_export(contact)
                writer.writerow(cleaned_contact)
        
        logging.info(f"Exported {len(contacts)} contacts to CSV: {output_path}")
        return str(output_path)

    async def _export_json(self, contacts: List[Dict], filename: str) -> str:
        """Export contacts to JSON format."""
        output_path = Path(self.config.output_dir) / f"{filename}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create export data structure
        export_data = {
            'metadata': {
                'export_timestamp': datetime.now().isoformat(),
                'total_contacts': len(contacts),
                'extractor_version': '1.0',
                'config': {
                    'max_depth': self.config.max_depth,
                    'validate_emails': self.config.validate_emails,
                    'extract_social': self.config.extract_social,
                    'use_javascript': self.config.use_javascript,
                }
            },
            'contacts': contacts
        }
        
        with open(output_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(export_data, jsonfile, indent=2, ensure_ascii=False, default=str)
        
        logging.info(f"Exported {len(contacts)} contacts to JSON: {output_path}")
        return str(output_path)

    async def _export_excel(self, contacts: List[Dict], filename: str) -> str:
        """Export contacts to Excel format with multiple sheets."""
        output_path = Path(self.config.output_dir) / f"{filename}.xlsx"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not contacts:
            # Create empty workbook
            pd.DataFrame().to_excel(output_path, index=False)
            return str(output_path)
        
        # Create DataFrames
        df_contacts = pd.DataFrame(contacts)
        
        # Clean and organize data
        df_contacts = self._prepare_dataframe_for_excel(df_contacts)
        
        # Create Excel writer with multiple sheets
        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            # Main contacts sheet
            df_contacts.to_excel(writer, sheet_name='Contacts', index=False)
            
            # Summary sheet
            summary_data = self._create_summary_data(contacts)
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Summary', index=False)
            
            # Statistics sheet
            stats_data = self._create_statistics_data(contacts)
            df_stats = pd.DataFrame(stats_data, index=[0])
            df_stats.to_excel(writer, sheet_name='Statistics', index=False)
            
            # Format the Excel file
            self._format_excel_sheets(writer, df_contacts, df_summary, df_stats)
        
        logging.info(f"Exported {len(contacts)} contacts to Excel: {output_path}")
        return str(output_path)

    def _clean_contact_for_export(self, contact: Dict) -> Dict:
        """Clean contact data for export (handle None values, long strings, etc.)."""
        cleaned = {}
        for key, value in contact.items():
            if value is None:
                cleaned[key] = ''
            elif isinstance(value, str):
                # Truncate very long strings and clean newlines
                cleaned[key] = value.replace('\n', ' ').replace('\r', ' ')[:1000]
            elif isinstance(value, (int, float)):
                cleaned[key] = value
            else:
                cleaned[key] = str(value)
        return cleaned

    def _prepare_dataframe_for_excel(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare DataFrame for Excel export."""
        # Define preferred column order
        preferred_columns = [
            'email', 'name', 'title', 'company', 'phone',
            'source_url', 'extraction_method', 'confidence',
            'validation_score', 'context'
        ]
        
        # Reorder columns
        available_columns = [col for col in preferred_columns if col in df.columns]
        other_columns = [col for col in df.columns if col not in preferred_columns]
        column_order = available_columns + other_columns
        
        df = df[column_order]
        
        # Clean data
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).replace('nan', '').replace('None', '')
        
        # Round numeric columns
        numeric_columns = ['confidence', 'validation_score']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').round(3)
        
        return df

    def _create_summary_data(self, contacts: List[Dict]) -> List[Dict]:
        """Create summary data for Excel export."""
        summary = []
        
        # Group by extraction method
        methods = {}
        for contact in contacts:
            method = contact.get('extraction_method', 'unknown')
            if method not in methods:
                methods[method] = 0
            methods[method] += 1
        
        for method, count in methods.items():
            summary.append({
                'Category': 'Extraction Method',
                'Type': method,
                'Count': count,
                'Percentage': f"{(count / len(contacts) * 100):.1f}%"
            })
        
        # Group by company
        companies = {}
        for contact in contacts:
            company = contact.get('company', 'Unknown')
            if company and company != 'Unknown':
                if company not in companies:
                    companies[company] = 0
                companies[company] += 1
        
        # Top 10 companies
        top_companies = sorted(companies.items(), key=lambda x: x[1], reverse=True)[:10]
        for company, count in top_companies:
            summary.append({
                'Category': 'Top Companies',
                'Type': company,
                'Count': count,
                'Percentage': f"{(count / len(contacts) * 100):.1f}%"
            })
        
        return summary

    def _create_statistics_data(self, contacts: List[Dict]) -> Dict:
        """Create statistics data for Excel export."""
        total_contacts = len(contacts)
        if total_contacts == 0:
            return {
                'Total Contacts': 0,
                'With Names': 0,
                'With Phone Numbers': 0,
                'With Job Titles': 0,
                'With Companies': 0,
                'Average Confidence': 0,
                'Average Validation Score': 0
            }
        
        with_names = sum(1 for c in contacts if c.get('name'))
        with_phones = sum(1 for c in contacts if c.get('phone'))
        with_titles = sum(1 for c in contacts if c.get('title'))
        with_companies = sum(1 for c in contacts if c.get('company'))
        
        avg_confidence = sum(c.get('confidence', 0) for c in contacts) / total_contacts
        avg_validation = sum(c.get('validation_score', 0) for c in contacts) / total_contacts
        
        return {
            'Total Contacts': total_contacts,
            'With Names': f"{with_names} ({with_names/total_contacts*100:.1f}%)",
            'With Phone Numbers': f"{with_phones} ({with_phones/total_contacts*100:.1f}%)",
            'With Job Titles': f"{with_titles} ({with_titles/total_contacts*100:.1f}%)",
            'With Companies': f"{with_companies} ({with_companies/total_contacts*100:.1f}%)",
            'Average Confidence': f"{avg_confidence:.3f}",
            'Average Validation Score': f"{avg_validation:.3f}"
        }

    def _format_excel_sheets(self, writer, df_contacts, df_summary, df_stats):
        """Complete Excel sheets formatting with proper styling."""
        workbook = writer.book
        
        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#D7E4BC',
            'border': 1
        })
        
        data_format = workbook.add_format({
            'text_wrap': True,
            'valign': 'top',
            'border': 1
        })
        
        # Format contacts sheet
        worksheet_contacts = writer.sheets['Contacts']
        
        # Set column widths
        column_widths = {
            'A': 30,  # email
            'B': 20,  # name
            'C': 25,  # title
            'D': 25,  # company
            'E': 15,  # phone
            'F': 40,  # source_url
            'G': 15,  # extraction_method
            'H': 10,  # confidence
            'I': 15,  # validation_score
            'J': 50   # context
        }
        
        for col, width in column_widths.items():
            worksheet_contacts.set_column(f'{col}:{col}', width)
        
        # Apply header format to contacts sheet
        for col_num, value in enumerate(df_contacts.columns.values):
            worksheet_contacts.write(0, col_num, value, header_format)
        
        # Format summary sheet
        worksheet_summary = writer.sheets['Summary']
        worksheet_summary.set_column('A:A', 20)
        worksheet_summary.set_column('B:B', 30)
        worksheet_summary.set_column('C:C', 10)
        worksheet_summary.set_column('D:D', 12)
        
        # Apply header format to summary
        for col_num, value in enumerate(df_summary.columns.values):
            worksheet_summary.write(0, col_num, value, header_format)
        
        # Format statistics sheet
        worksheet_stats = writer.sheets['Statistics']
        worksheet_stats.set_column('A:Z', 20)
        
        # Apply header format to statistics
        for col_num, value in enumerate(df_stats.columns.values):
            worksheet_stats.write(0, col_num, value, header_format)

    async def export_to_crm(self, contacts: List[Dict]) -> bool:
        """Export contacts to CRM systems (if configured)."""
        try:
            success = True
            
            # Export to Salesforce
            if self.config.salesforce_username:
                sf_success = await self._export_to_salesforce(contacts)
                success = success and sf_success
            
            # Export to HubSpot
            if self.config.hubspot_api_key:
                hs_success = await self._export_to_hubspot(contacts)
                success = success and hs_success
            
            return success
        except Exception as e:
            logging.error(f"Error exporting to CRM: {e}")
            return False

    async def _export_to_salesforce(self, contacts: List[Dict]) -> bool:
        """Export contacts to Salesforce."""
        try:
            # Import here to avoid dependency issues if not used
            from simple_salesforce import Salesforce
            
            sf = Salesforce(
                username=self.config.salesforce_username,
                password=self.config.salesforce_password,
                security_token=self.config.salesforce_token
            )
            
            successful_exports = 0
            for contact in contacts:
                try:
                    # Map to Salesforce Lead object
                    lead_data = {
                        'Email': contact.get('email'),
                        'FirstName': contact.get('name', '').split()[0] if contact.get('name') else '',
                        'LastName': ' '.join(contact.get('name', '').split()[1:]) if contact.get('name') and len(contact.get('name', '').split()) > 1 else 'Unknown',
                        'Title': contact.get('title', ''),
                        'Company': contact.get('company', 'Unknown'),
                        'Phone': contact.get('phone', ''),
                        'LeadSource': 'Web Scraping',
                        'Description': f"Extracted from: {contact.get('source_url', '')}"
                    }
                    
                    # Remove empty fields
                    lead_data = {k: v for k, v in lead_data.items() if v}
                    
                    # Create lead
                    result = sf.Lead.create(lead_data)
                    if result['success']:
                        successful_exports += 1
                        
                except Exception as e:
                    logging.warning(f"Failed to export contact {contact.get('email')} to Salesforce: {e}")
            
            logging.info(f"Exported {successful_exports}/{len(contacts)} contacts to Salesforce")
            return successful_exports > 0
            
        except Exception as e:
            logging.error(f"Salesforce export failed: {e}")
            return False

    async def _export_to_hubspot(self, contacts: List[Dict]) -> bool:
        """Export contacts to HubSpot."""
        try:
            # Import here to avoid dependency issues if not used
            from hubspot import HubSpot
            from hubspot.crm.contacts import SimplePublicObjectInput
            
            api_client = HubSpot(access_token=self.config.hubspot_api_key)
            
            successful_exports = 0
            for contact in contacts:
                try:
                    # Map to HubSpot contact properties
                    properties = {
                        'email': contact.get('email'),
                        'firstname': contact.get('name', '').split()[0] if contact.get('name') else '',
                        'lastname': ' '.join(contact.get('name', '').split()[1:]) if contact.get('name') and len(contact.get('name', '').split()) > 1 else '',
                        'jobtitle': contact.get('title', ''),
                        'company': contact.get('company', ''),
                        'phone': contact.get('phone', ''),
                        'hs_lead_status': 'NEW',
                        'lifecyclestage': 'lead'
                    }
                    
                    # Remove empty fields
                    properties = {k: v for k, v in properties.items() if v}
                    
                    # Create contact
                    simple_public_object_input = SimplePublicObjectInput(properties=properties)
                    result = api_client.crm.contacts.basic_api.create(simple_public_object_input)
                    
                    if result:
                        successful_exports += 1
                        
                except Exception as e:
                    logging.warning(f"Failed to export contact {contact.get('email')} to HubSpot: {e}")
            
            logging.info(f"Exported {successful_exports}/{len(contacts)} contacts to HubSpot")
            return successful_exports > 0
            
        except Exception as e:
            logging.error(f"HubSpot export failed: {e}")
            return False
