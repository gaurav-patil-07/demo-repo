
# from django.core.management.base import BaseCommand
# from mvqc.models import FileRecord, PageData, ExceptionData
# import os
# import re
# import shutil
# import fitz  # PyMuPDF
# import pytesseract  # type: ignore
# from PIL import Image  # type: ignore
# import io
# import platform
# from datetime import datetime
# from django.db import transaction
# import logging
# import time


# class Command(BaseCommand):
#     help = 'Process all PDFs in Page7 folder and extract OTS/BT Change data to database'

#     def add_arguments(self, parser):
#         parser.add_argument('--folder', type=str, default='Data4',
#                             help='Folder to process: Data1, Data2, Data3 or Data4')

#     def handle(self, *args, **options):

#         # === CONFIG ===
#         from django.conf import settings
#         folder = options.get('folder') or 'Data4'
#         PDFFilePath = os.path.join(settings.BASE_DIR, "output", folder, f"{folder}_Output", "Page7")

#         # === LOGGING — file only, no console ===
#         log_folder = os.path.join(settings.BASE_DIR, "mvqc", "logs")
#         os.makedirs(log_folder, exist_ok=True)
#         today    = datetime.now().strftime('%Y-%m-%d')
#         log_file = os.path.join(log_folder, f"page7_{today}.log")

#         logger = logging.getLogger(__name__)
#         logger.setLevel(logging.INFO)

#         if not logger.handlers:
#             file_handler = logging.FileHandler(log_file)
#             file_handler.setLevel(logging.INFO)
#             file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
#             logger.addHandler(file_handler)

#         # === Tesseract configuration for Windows and Linux ===
#         if platform.system() == 'Windows':
#             pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

#         # ─────────────────────────────────────────
#         # HELPERS
#         # ─────────────────────────────────────────
#         def has_blank_values(data_dict):
#             for key, value in data_dict.items():
#                 if value == "" or value is None or (isinstance(value, str) and value.strip() == ""):
#                     return True
#             return False

#         def merge_json(old_json, new_json):
#             merged = old_json.copy()
#             for key, new_value in new_json.items():
#                 if new_value and new_value != "" and (not isinstance(new_value, str) or new_value.strip() != ""):
#                     merged[key] = new_value
#             return merged

#         def extract_page_number(filename):
#             try:
#                 match = re.search(r'Page(\d+)', filename, re.IGNORECASE)
#                 return int(match.group(1)) if match else 7
#             except:
#                 return 7

#         def extract_lan_id_from_filename(file_name):
#             filename_no_ext = os.path.splitext(file_name)[0]
#             parts = filename_no_ext.split("_")
#             if parts[0].lower().startswith("page"):
#                 return parts[1] if len(parts) > 1 else ""
#             return parts[0] if parts else ""

#         def extract_lender_name(text):
#             """Shared lender name extraction logic for both BT Change and OTS."""
#             lender_match = re.search(
#                 r"currently active with\s+([^\n\r]+?)(?:Lenders'? Bank name|$)",
#                 text, re.IGNORECASE | re.DOTALL
#             )
#             if lender_match:
#                 lender_text = lender_match.group(1).strip()
#                 lender_text = re.split(r"Lenders'? Bank name", lender_text, flags=re.IGNORECASE)[0].strip()
#                 lender_text = re.sub(r'[-_]+$', '', lender_text).strip()
#                 return lender_text

#             manager_match = re.search(r"The Manager,?\s+([^\n\r]+)", text, re.IGNORECASE)
#             if manager_match:
#                 return manager_match.group(1).strip()

#             fallback_match = re.search(r"([A-Za-z\s&]+?(?:Pvt\s*Ltd|Limited))", text, re.IGNORECASE)
#             if fallback_match:
#                 return fallback_match.group(1).strip()

#             return ""

#         def extract_bt_change(text):
#             """Extraction logic for BT Change PDFs."""
#             data = {
#                 "PDFType":           "BT Change",
#                 "LoanAccountNumber": "",
#                 "TOS":               "",
#                 "Lender_Name":       "",
#                 "Status":            "Failed",
#                 "Message":           "Extraction failed.",
#             }
#             lan_match = re.search(r"Loan Account Number[\s:-]*([A-Za-z0-9]+)", text, re.IGNORECASE)
#             if lan_match:
#                 data["LoanAccountNumber"] = lan_match.group(1).strip()

#             amt_match = re.search(
#                 r"(Outstanding Amount|Settlement Amount)[^\d]*(\d+(?:,\d+)*\.?\d*)",
#                 text, re.IGNORECASE
#             )
#             if amt_match:
#                 data["TOS"] = amt_match.group(2).replace(",", "").strip()

#             data["Lender_Name"] = extract_lender_name(text)

#             if data["LoanAccountNumber"] or data["TOS"] or data["Lender_Name"]:
#                 data["Status"]  = "Success"
#                 data["Message"] = "BT Change details extracted."
#             return data

#         def extract_ots(text):
#             """Extraction logic for OTS PDFs."""
#             data = {
#                 "PDFType":           "OTS",
#                 "LoanAccountNumber": "",
#                 "TOS":               "",
#                 "Lender_Name":       "",
#                 "Status":            "Failed",
#                 "Message":           "Extraction failed.",
#             }
#             # NEW: Extract from "Existing loan account number - MVDELPL4001015981"
#             lan_match = re.search(
#                 r"Existing loan account number\s*[-:]\s*([A-Z0-9]+)",
#                 text, re.IGNORECASE
#             )
#             if lan_match:
#                 data["LoanAccountNumber"] = lan_match.group(1).strip()

#             # OLD CODE (COMMENTED FOR REFERENCE)
#             # lan_match = re.search(
#             #     r"(?:Existing loan application number|Loan Account Number)[^\d]*([A-Za-z0-9]+)",
#             #     text, re.IGNORECASE
#             # )
#             # if lan_match:
#             #     data["LoanAccountNumber"] = lan_match.group(1).strip()

#             amt_match = re.search(
#                 r"(?:outstanding loan amount)[^\d]*(\d+(?:,\d+)*\.?\d*)",
#                 text, re.IGNORECASE
#             )
#             if amt_match:
#                 data["TOS"] = amt_match.group(1).replace(",", "").strip()

#             data["Lender_Name"] = extract_lender_name(text)

#             if data["LoanAccountNumber"] or data["TOS"] or data["Lender_Name"]:
#                 data["Status"]  = "Success"
#                 data["Message"] = "OTS details extracted."
#             return data

#         def save_to_page_data_and_cleanup(file_record, page_number, extracted_data, file_name, pdf_path, source_label=""):
#             """Save to PageData, delete ExceptionData, move file to archive."""
#             PageData.objects.update_or_create(
#                 pdf=file_record,
#                 page_number=page_number,
#                 defaults={'json_data': extracted_data}
#             )
#             ExceptionData.objects.filter(pdf=file_record, file=file_name).delete()
#             if os.path.exists(pdf_path):
#                 shutil.move(pdf_path, os.path.join(archive_folder, file_name))
#             logger.info(f"{file_name}: Saved to PageData, ExceptionData deleted, archived {source_label}")

#         def save_to_exception(file_record, page_number, extracted_data, file_name, pdf_path, from_exception_folder=False):
#             """Save partial data to PageData, save/update ExceptionData, move to exception folder if needed."""
#             page_data_obj, _ = PageData.objects.update_or_create(
#                 pdf=file_record,
#                 page_number=page_number,
#                 defaults={'json_data': extracted_data}
#             )
#             exception_obj, ex_created = ExceptionData.objects.get_or_create(
#                 pdf=file_record,
#                 file=file_name,
#                 defaults={
#                     'exception_json': extracted_data,
#                     'pageid': page_data_obj
#                 }
#             )
#             if not ex_created:
#                 exception_obj.exception_json = extracted_data
#                 exception_obj.pageid         = page_data_obj
#                 exception_obj.save()

#             if not from_exception_folder:
#                 if os.path.exists(pdf_path):
#                     shutil.move(pdf_path, os.path.join(exception_folder, file_name))
#             logger.info(f"{file_name}: Saved to ExceptionData {'(updated)' if not ex_created else '(created)'}")

#         # ─────────────────────────────────────────
#         # CORE EXTRACTION
#         # ─────────────────────────────────────────
#         def process_single_pdf(pdf_path, file_name, file_record, is_retry=False):
#             try:
#                 lan_id      = extract_lan_id_from_filename(file_name)
#                 page_number = extract_page_number(os.path.splitext(file_name)[0])

#                 headers = [
#                     "LAN_ID", "LoanAccountNumber", "TOS",
#                     "Lender_Name", "PDFType", "Status", "Message"
#                 ]
#                 extracted_data = {h: "" for h in headers}
#                 extracted_data["LAN_ID"]  = lan_id
#                 extracted_data["PDFType"] = "Unknown"
#                 extracted_data["Status"]  = "Failed"
#                 extracted_data["Message"] = "Unrecognized document type."

#                 # --- OCR extraction via PyMuPDF + Tesseract ---
#                 full_text = ""
#                 doc = None
#                 try:
#                     doc = fitz.open(pdf_path)
#                     for page in doc:
#                         pix = page.get_pixmap(dpi=300)
#                         img = Image.open(io.BytesIO(pix.tobytes()))
#                         full_text += pytesseract.image_to_string(img) + "\n"
#                 finally:
#                     if doc:
#                         doc.close()

#                 if not full_text.strip():
#                     raise ValueError("No text extracted from OCR.")

#                 # --- Classify and extract ---
#                 if "Existing loan application number" in full_text or "Existing outstanding loan amount" in full_text:
#                     result = extract_ots(full_text)
#                 elif "Closure of my existing Loan Account Number" in full_text or "Outstanding Amount" in full_text:
#                     result = extract_bt_change(full_text)
#                 else:
#                     result = {
#                         "PDFType": "Unknown",
#                         "Status":  "Failed",
#                         "Message": "Unrecognized document type.",
#                         "LoanAccountNumber": "",
#                         "TOS":               "",
#                         "Lender_Name":       "",
#                     }

#                 extracted_data.update(result)

#                 # --- Retry merge ---
#                 if is_retry:
#                     try:
#                         old_exception = ExceptionData.objects.filter(
#                             pdf=file_record, file=file_name
#                         ).first()
#                         if old_exception:
#                             extracted_data = merge_json(old_exception.exception_json, extracted_data)
#                     except Exception as e:
#                         logger.warning(f"Could not merge with old data for {file_name}: {e}")

#                 return extracted_data, page_number

#             except Exception as e:
#                 logger.error(f"Error processing {file_name}: {e}")
#                 return None, None

#         # ─────────────────────────────────────────
#         # MAIN
#         # ─────────────────────────────────────────
#         try:
#             total_start_time = time.time()
#             self.stdout.write("INFO - Starting Page7 processing...")

#             if not os.path.exists(PDFFilePath):
#                 os.makedirs(PDFFilePath, exist_ok=True)

#             archive_folder   = os.path.join(PDFFilePath, 'archive')
#             exception_folder = os.path.join(PDFFilePath, 'exception')
#             os.makedirs(archive_folder, exist_ok=True)
#             os.makedirs(exception_folder, exist_ok=True)

#             # ─────────────────────────────────────
#             # STEP 1: First pass
#             # ─────────────────────────────────────
#             processed_count = 0
#             exception_count = 0

#             pdf_files   = [f for f in os.listdir(PDFFilePath) if f.lower().endswith(".pdf")]
#             total_files = len(pdf_files)
#             logger.info(f"Found {total_files} PDF(s) in main folder")
#             self.stdout.write(f"PDF files found in Page7 folder: {total_files}")

#             for idx, file_name in enumerate(pdf_files, 1):
#                 pdf_path        = os.path.join(PDFFilePath, file_name)
#                 lan_id          = "Unknown"
#                 page_start_time = time.time()

#                 try:
#                     lan_id = extract_lan_id_from_filename(file_name)

#                     with transaction.atomic():
#                         try:
#                             file_record = FileRecord.objects.get(lan_id=lan_id)
#                         except FileRecord.DoesNotExist:
#                             logger.error(f"No FileRecord for LAN_ID: {lan_id}. Skipping {file_name}")
#                             self.stdout.write(f"{idx}/{total_files} Processing: {lan_id} — FileRecord not found, skipped")
#                             continue
#                         except FileRecord.MultipleObjectsReturned:
#                             file_record = FileRecord.objects.filter(lan_id=lan_id).first()
#                             logger.warning(f"Multiple FileRecords for LAN_ID: {lan_id}. Using ID: {file_record.id}")

#                         extracted_data, page_number = process_single_pdf(
#                             pdf_path, file_name, file_record, is_retry=False
#                         )

#                         if extracted_data is None:
#                             raise Exception("process_single_pdf returned None")

#                         if has_blank_values(extracted_data):
#                             save_to_exception(
#                                 file_record, page_number, extracted_data,
#                                 file_name, pdf_path,
#                                 from_exception_folder=False
#                             )
#                             exception_count += 1
#                         else:
#                             save_to_page_data_and_cleanup(
#                                 file_record, page_number, extracted_data,
#                                 file_name, pdf_path,
#                                 source_label="(first pass)"
#                             )
#                             processed_count += 1

#                     page_elapsed = int(time.time() - page_start_time)
#                     self.stdout.write(f"{idx}/{total_files} Processing: {lan_id} {page_elapsed}s")

#                 except Exception as e:
#                     logger.error(f"Failed to process {file_name}: {e}")
#                     if os.path.exists(pdf_path):
#                         shutil.move(pdf_path, os.path.join(exception_folder, file_name))
#                     exception_count += 1
#                     page_elapsed = int(time.time() - page_start_time)
#                     self.stdout.write(f"{idx}/{total_files} Processing: {lan_id} ERROR {page_elapsed}s")

#             logger.info(f"Step 1 done — Archived: {processed_count}, Exception: {exception_count}")

#             # ─────────────────────────────────────
#             # STEP 2: Retry exception folder (3x)
#             # ─────────────────────────────────────
#             MAX_RETRIES          = 1
#             retry_success        = 0
#             retry_failed         = 0
#             final_retry_archived = 0

#             for retry_num in range(1, MAX_RETRIES + 1):
#                 logger.info(f"=== RETRY {retry_num}/{MAX_RETRIES} ===")

#                 exception_files = [f for f in os.listdir(exception_folder) if f.lower().endswith(".pdf")]
#                 if not exception_files:
#                     logger.info("Exception folder empty — stopping retries")
#                     break

#                 total_exceptions = len(exception_files)

#                 for ex_idx, file_name in enumerate(exception_files, 1):
#                     pdf_path        = os.path.join(exception_folder, file_name)
#                     lan_id          = "Unknown"
#                     page_start_time = time.time()

#                     try:
#                         lan_id = extract_lan_id_from_filename(file_name)

#                         with transaction.atomic():
#                             try:
#                                 file_record = FileRecord.objects.get(lan_id=lan_id)
#                             except FileRecord.DoesNotExist:
#                                 logger.error(f"No FileRecord for LAN_ID: {lan_id}. Skipping retry.")
#                                 continue
#                             except FileRecord.MultipleObjectsReturned:
#                                 file_record = FileRecord.objects.filter(lan_id=lan_id).first()
#                                 logger.warning(f"Multiple FileRecords for LAN_ID: {lan_id}. Using ID: {file_record.id}")

#                             extracted_data, page_number = process_single_pdf(
#                                 pdf_path, file_name, file_record, is_retry=True
#                             )

#                             if extracted_data is None:
#                                 raise Exception("process_single_pdf returned None on retry")

#                             if has_blank_values(extracted_data):
#                                 if retry_num == MAX_RETRIES:
#                                     save_to_page_data_and_cleanup(
#                                         file_record, page_number, extracted_data,
#                                         file_name, pdf_path,
#                                         source_label=f"(final retry {retry_num}, blanks remain)"
#                                     )
#                                     final_retry_archived += 1
#                                 else:
#                                     save_to_exception(
#                                         file_record, page_number, extracted_data,
#                                         file_name, pdf_path,
#                                         from_exception_folder=True
#                                     )
#                                     retry_failed += 1
#                             else:
#                                 save_to_page_data_and_cleanup(
#                                     file_record, page_number, extracted_data,
#                                     file_name, pdf_path,
#                                     source_label=f"(retry {retry_num} success)"
#                                 )
#                                 retry_success += 1

#                         page_elapsed = int(time.time() - page_start_time)
#                         self.stdout.write(f"  Retry {retry_num} {ex_idx}/{total_exceptions}: {lan_id} {page_elapsed}s")

#                     except Exception as e:
#                         logger.error(f"Retry {retry_num} failed for {file_name}: {e}")
#                         retry_failed += 1
#                         page_elapsed = int(time.time() - page_start_time)
#                         self.stdout.write(f"  Retry {retry_num} {ex_idx}/{total_exceptions}: {lan_id} ERROR {page_elapsed}s")

#                 logger.info(f"Retry {retry_num} done — Success: {retry_success}, Final archived: {final_retry_archived}, Still in exception: {retry_failed}")

#             # ─────────────────────────────────────
#             # SUMMARY
#             # ─────────────────────────────────────
#             total_elapsed  = time.time() - total_start_time
#             minutes        = int(total_elapsed // 60)
#             seconds        = int(total_elapsed % 60)
#             total_archived = processed_count + retry_success + final_retry_archived

#             self.stdout.write(f"\n  First pass archived  : {processed_count}")
#             self.stdout.write(f"  Retry archived       : {retry_success}")
#             self.stdout.write(f"  Final retry archived : {final_retry_archived}")
#             self.stdout.write(f"  Total archived       : {total_archived}")
#             self.stdout.write(f"  Total time           : {minutes}m {seconds}s")

#             logger.info(f"Page7 complete. Total archived: {total_archived}, Time: {minutes}m {seconds}s")

#         except Exception as e:
#             logger.error(f"Main block error: {e}")
#             self.stdout.write(self.style.ERROR(f"Error: {e}"))


# # -------------------------------------new

from django.core.management.base import BaseCommand
from mvqc.models import FileRecord, PageData, ExceptionData
import os
import re
import shutil
import fitz  # PyMuPDF
import pytesseract  # type: ignore
from PIL import Image  # type: ignore
import io
import platform
from datetime import datetime
from django.db import transaction
import logging
import time


class Command(BaseCommand):
    help = 'Process all PDFs in Page7 folder and extract OTS/BT Change data to database'

    def add_arguments(self, parser):
        parser.add_argument('--folder', type=str, default='Data4',
                            help='Folder to process: Data1, Data2, Data3 or Data4')

    def handle(self, *args, **options):

        # === CONFIG ===
        from django.conf import settings
        folder = options.get('folder') or 'Data4'
        PDFFilePath = os.path.join(settings.BASE_DIR, "output", folder, f"{folder}_Output", "Page7")
        # PDFFilePath = r"D:\Django_mvqc\output\Data1\Data1_Output\page7"

        # === LOGGING — file only, no console ===
        log_folder = os.path.join(settings.BASE_DIR, "mvqc", "logs")
        try:
            os.makedirs(log_folder, exist_ok=True)
        except Exception:
            pass  # Continue without logging if folder creation fails

        today    = datetime.now().strftime('%Y-%m-%d')
        log_file = os.path.join(log_folder, f"page7_{today}.log")

        logger = logging.getLogger('page7')
        logger.setLevel(logging.INFO)
        logger.propagate = False  # Prevent duplicate logs

        if not logger.handlers:
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                logger.addHandler(file_handler)
            except Exception:
                pass  # Continue without file logging if it fails

        # === Tesseract configuration for Windows and Linux ===
        if platform.system() == 'Windows':
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

        # ─────────────────────────────────────────
        # HELPERS
        # ─────────────────────────────────────────
        def has_blank_values(data_dict):
            for key, value in data_dict.items():
                if value == "" or value is None or (isinstance(value, str) and value.strip() == ""):
                    return True
            return False

        def merge_json(old_json, new_json):
            merged = old_json.copy()
            for key, new_value in new_json.items():
                if new_value and new_value != "" and (not isinstance(new_value, str) or new_value.strip() != ""):
                    merged[key] = new_value
            return merged

        def extract_page_number(filename):
            try:
                match = re.search(r'Page(\d+)', filename, re.IGNORECASE)
                return int(match.group(1)) if match else 7
            except:
                return 7

        def extract_lan_id_from_filename(file_name):
            filename_no_ext = os.path.splitext(file_name)[0]
            parts = filename_no_ext.split("_")
            if parts[0].lower().startswith("page"):
                return parts[1] if len(parts) > 1 else ""
            return parts[0] if parts else ""

        def extract_lender_name(text):
            """Shared lender name extraction logic for both BT Change and OTS."""
            # Pattern 1: "currently active with <name>" followed by "Lenders' Bank name"
            # Improved to handle underscores and capture full company names
            lender_match = re.search(
                r"currently active with\s+([^\n\r]+?)(?:\s*[-_\s]*\s*Lenders'?\s*Bank\s*name|\s*[-_\s]*\s*Lender'?s?\s*Bank|$)",
                text, re.IGNORECASE | re.DOTALL
            )
            if lender_match:
                lender_text = lender_match.group(1).strip()
                # Remove trailing underscores, dashes, and extra whitespace
                lender_text = re.sub(r'[-_\s]+$', '', lender_text).strip()
                # Remove any underscores or dashes within the text (OCR artifacts)
                lender_text = re.sub(r'_{2,}', ' ', lender_text).strip()
                lender_text = re.sub(r'-{2,}', ' ', lender_text).strip()
                # Clean up multiple spaces
                lender_text = re.sub(r'\s+', ' ', lender_text).strip()
                # Exclude "Clix Capital" — that's the document issuer, not the lender
                if lender_text and "clix capital" not in lender_text.lower() and len(lender_text) > 3:
                    return lender_text

            # Pattern 2: "The Manager, <name>"
            manager_match = re.search(r"The Manager,?\s+([^\n\r]+)", text, re.IGNORECASE)
            if manager_match:
                name = manager_match.group(1).strip()
                name = re.sub(r'[-_\s]+$', '', name).strip()
                if "clix capital" not in name.lower() and len(name) > 3:
                    return name

            # Pattern 3: Match company names with "Private Limited"
            # Find all matches and take the shortest one to avoid capturing extra text
            # Case-sensitive to ensure we start with a capital letter
            fallback_matches = re.findall(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z]?[A-Za-z&]+){1,4}\s+Private\s+Limited)\b", text)
            if fallback_matches:
                name = min(fallback_matches, key=len).strip()
                name = re.sub(r'\s+', ' ', name).strip()
                if "clix capital" not in name.lower() and len(name) > 3:
                    return name

            # Pattern 4: Match "Pvt Ltd" or "Pvt. Ltd."
            fallback_matches2 = re.findall(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z]?[A-Za-z&]+){1,4}\s+Pvt\.?\s*Ltd\.?)\b", text)
            if fallback_matches2:
                name = min(fallback_matches2, key=len).strip()
                name = re.sub(r'\s+', ' ', name).strip()
                if "clix capital" not in name.lower() and len(name) > 3:
                    return name

            # Pattern 5: Match "Finance Private Limited" or "Finance Limited"
            fallback_matches3 = re.findall(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z]?[A-Za-z&]+){1,3}\s+Finance\s+(?:Private\s+)?Limited)\b", text)
            if fallback_matches3:
                name = min(fallback_matches3, key=len).strip()
                name = re.sub(r'\s+', ' ', name).strip()
                if "clix capital" not in name.lower() and len(name) > 3:
                    return name

            return ""


        def extract_bt_change(text):
            """Extraction logic for BT Change PDFs."""
            data = {
                "PDFType":           "BT Change",
                "LoanAccountNumber": "",
                "TOS":               "",
                "Lender_Name":       "",
                "Status":            "Failed",
                "Message":           "Extraction failed.",
            }
            lan_match = re.search(r"Loan Account Number[\s:-]*([A-Za-z0-9]+)", text, re.IGNORECASE)
            if lan_match:
                data["LoanAccountNumber"] = lan_match.group(1).strip()

            amt_match = re.search(
                r"(Outstanding Amount|Settlement Amount)[^\d]*(\d+(?:,\d+)*\.?\d*)",
                text, re.IGNORECASE
            )
            if amt_match:
                data["TOS"] = amt_match.group(2).replace(",", "").strip()

            data["Lender_Name"] = extract_lender_name(text)

            if data["LoanAccountNumber"] or data["TOS"] or data["Lender_Name"]:
                data["Status"]  = "Success"
                data["Message"] = "BT Change details extracted."
            return data

        def extract_ots(text):
            """Extraction logic for OTS PDFs."""
            data = {
                "PDFType":           "OTS",
                "LoanAccountNumber": "",
                "TOS":               "",
                "Lender_Name":       "",
                "Status":            "Failed",
                "Message":           "Extraction failed.",
            }
            # NEW: Extract from "Existing loan account number - MVDELPL4001015981"
            lan_match = re.search(
                r"Existing loan account number\s*[-:]\s*([A-Z0-9]+)",
                text, re.IGNORECASE
            )
            if lan_match:
                data["LoanAccountNumber"] = lan_match.group(1).strip()

            # OLD CODE (COMMENTED FOR REFERENCE)
            # lan_match = re.search(
            #     r"(?:Existing loan application number|Loan Account Number)[^\d]*([A-Za-z0-9]+)",
            #     text, re.IGNORECASE
            # )
            # if lan_match:
            #     data["LoanAccountNumber"] = lan_match.group(1).strip()

            amt_match = re.search(
                r"(?:outstanding loan amount)[^\d]*(\d+(?:,\d+)*\.?\d*)",
                text, re.IGNORECASE
            )
            if amt_match:
                data["TOS"] = amt_match.group(1).replace(",", "").strip()

            data["Lender_Name"] = extract_lender_name(text)

            if data["LoanAccountNumber"] or data["TOS"] or data["Lender_Name"]:
                data["Status"]  = "Success"
                data["Message"] = "OTS details extracted."
            return data

        def save_to_page_data_and_cleanup(file_record, page_number, extracted_data, file_name, pdf_path, source_label=""):
            """Save to PageData, delete ExceptionData, move file to archive."""
            PageData.objects.update_or_create(
                pdf=file_record,
                page_number=page_number,
                defaults={'json_data': extracted_data}
            )
            ExceptionData.objects.filter(pdf=file_record, file=file_name).delete()
            if os.path.exists(pdf_path):
                shutil.move(pdf_path, os.path.join(archive_folder, file_name))
            logger.info(f"{file_name}: Saved to PageData, ExceptionData deleted, archived {source_label}")

        def save_to_exception(file_record, page_number, extracted_data, file_name, pdf_path, from_exception_folder=False):
            """Save partial data to PageData, save/update ExceptionData, move to exception folder if needed."""
            page_data_obj, _ = PageData.objects.update_or_create(
                pdf=file_record,
                page_number=page_number,
                defaults={'json_data': extracted_data}
            )
            exception_obj, ex_created = ExceptionData.objects.get_or_create(
                pdf=file_record,
                file=file_name,
                defaults={
                    'exception_json': extracted_data,
                    'pageid': page_data_obj
                }
            )
            if not ex_created:
                exception_obj.exception_json = extracted_data
                exception_obj.pageid         = page_data_obj
                exception_obj.save()

            if not from_exception_folder:
                if os.path.exists(pdf_path):
                    shutil.move(pdf_path, os.path.join(exception_folder, file_name))
            logger.info(f"{file_name}: Saved to ExceptionData {'(updated)' if not ex_created else '(created)'}")

        # ─────────────────────────────────────────
        # CORE EXTRACTION
        # ─────────────────────────────────────────
        def process_single_pdf(pdf_path, file_name, file_record, is_retry=False):
            try:
                lan_id      = extract_lan_id_from_filename(file_name)
                page_number = extract_page_number(os.path.splitext(file_name)[0])

                headers = [
                    "LAN_ID", "LoanAccountNumber", "TOS",
                    "Lender_Name", "PDFType", "Status", "Message"
                ]
                extracted_data = {h: "" for h in headers}
                extracted_data["LAN_ID"]  = lan_id
                extracted_data["PDFType"] = "Unknown"
                extracted_data["Status"]  = "Failed"
                extracted_data["Message"] = "Unrecognized document type."

                # --- OCR extraction via PyMuPDF + Tesseract ---
                full_text = ""
                doc = None
                try:
                    doc = fitz.open(pdf_path)
                    for page in doc:
                        pix = page.get_pixmap(dpi=300)
                        img = Image.open(io.BytesIO(pix.tobytes()))
                        full_text += pytesseract.image_to_string(img) + "\n"
                finally:
                    if doc:
                        doc.close()

                if not full_text.strip():
                    raise ValueError("No text extracted from OCR.")

                # --- Classify and extract ---
                if "Existing loan application number" in full_text or "Existing outstanding loan amount" in full_text:
                    result = extract_ots(full_text)
                elif "Closure of my existing Loan Account Number" in full_text or "Outstanding Amount" in full_text:
                    result = extract_bt_change(full_text)
                else:
                    result = {
                        "PDFType": "Unknown",
                        "Status":  "Failed",
                        "Message": "Unrecognized document type.",
                        "LoanAccountNumber": "",
                        "TOS":               "",
                        "Lender_Name":       "",
                    }

                extracted_data.update(result)

                # --- Retry merge ---
                if is_retry:
                    try:
                        old_exception = ExceptionData.objects.filter(
                            pdf=file_record, file=file_name
                        ).first()
                        if old_exception:
                            extracted_data = merge_json(old_exception.exception_json, extracted_data)
                    except Exception as e:
                        logger.warning(f"Could not merge with old data for {file_name}: {e}")

                return extracted_data, page_number

            except Exception as e:
                logger.error(f"Error processing {file_name}: {e}")
                return None, None

        # ─────────────────────────────────────────
        # MAIN
        # ─────────────────────────────────────────
        try:
            total_start_time = time.time()
            self.stdout.write("INFO - Starting Page7 processing...")

            if not os.path.exists(PDFFilePath):
                os.makedirs(PDFFilePath, exist_ok=True)

            archive_folder   = os.path.join(PDFFilePath, 'archive')
            exception_folder = os.path.join(PDFFilePath, 'exception')
            os.makedirs(archive_folder, exist_ok=True)
            os.makedirs(exception_folder, exist_ok=True)

            # ─────────────────────────────────────
            # STEP 1: First pass
            # ─────────────────────────────────────
            processed_count = 0
            exception_count = 0

            # Get all PDFs from main folder, excluding those already archived
            all_pdf_files = [f for f in os.listdir(PDFFilePath) if f.lower().endswith(".pdf")]
            pdf_files = [f for f in all_pdf_files if not os.path.exists(os.path.join(archive_folder, f))]
            archived_count = len(all_pdf_files) - len(pdf_files)
            if archived_count > 0:
                logger.info(f"Skipped {archived_count} already archived file(s)")
                self.stdout.write(f"INFO - Skipped {archived_count} already archived file(s)")
            total_files = len(pdf_files)
            logger.info(f"Found {total_files} PDF(s) to process (excluding archived)")
            self.stdout.write(f"PDF files found in Page7 folder: {total_files}")

            for idx, file_name in enumerate(pdf_files, 1):
                pdf_path        = os.path.join(PDFFilePath, file_name)
                lan_id          = "Unknown"
                page_start_time = time.time()

                try:
                    lan_id = extract_lan_id_from_filename(file_name)

                    with transaction.atomic():
                        try:
                            file_record = FileRecord.objects.get(lan_id=lan_id)
                        except FileRecord.DoesNotExist:
                            logger.error(f"No FileRecord for LAN_ID: {lan_id}. Skipping {file_name}")
                            self.stdout.write(f"{idx}/{total_files} Processing: {lan_id} — FileRecord not found, skipped")
                            continue
                        except FileRecord.MultipleObjectsReturned:
                            file_record = FileRecord.objects.filter(lan_id=lan_id).first()
                            logger.warning(f"Multiple FileRecords for LAN_ID: {lan_id}. Using ID: {file_record.id}")

                        # Skip if already successfully processed (PageData exists and no ExceptionData)
                        tentative_page_number = extract_page_number(os.path.splitext(file_name)[0])
                        already_done = (
                            PageData.objects.filter(pdf=file_record, page_number=tentative_page_number).exists()
                            and not ExceptionData.objects.filter(pdf=file_record, file=file_name).exists()
                        )
                        if already_done:
                            logger.info(f"{file_name}: Already processed, skipping.")
                            self.stdout.write(f"{idx}/{total_files} Skipping (already processed): {lan_id}")
                            # Move to archive if still sitting in main folder
                            if os.path.exists(pdf_path):
                                shutil.move(pdf_path, os.path.join(archive_folder, file_name))
                            processed_count += 1
                            continue

                        extracted_data, page_number = process_single_pdf(
                            pdf_path, file_name, file_record, is_retry=False
                        )

                        if extracted_data is None:
                            raise Exception("process_single_pdf returned None")

                        if has_blank_values(extracted_data):
                            save_to_exception(
                                file_record, page_number, extracted_data,
                                file_name, pdf_path,
                                from_exception_folder=False
                            )
                            exception_count += 1
                        else:
                            save_to_page_data_and_cleanup(
                                file_record, page_number, extracted_data,
                                file_name, pdf_path,
                                source_label="(first pass)"
                            )
                            processed_count += 1

                    page_elapsed = int(time.time() - page_start_time)
                    self.stdout.write(f"{idx}/{total_files} Processing: {lan_id} {page_elapsed}s")

                except Exception as e:
                    logger.error(f"Failed to process {file_name}: {e}")
                    if os.path.exists(pdf_path):
                        shutil.move(pdf_path, os.path.join(exception_folder, file_name))
                    exception_count += 1
                    page_elapsed = int(time.time() - page_start_time)
                    self.stdout.write(f"{idx}/{total_files} Processing: {lan_id} ERROR {page_elapsed}s")

            logger.info(f"Step 1 done — Archived: {processed_count}, Exception: {exception_count}")

            # ─────────────────────────────────────
            # STEP 2: Retry exception folder (3x)
            # ─────────────────────────────────────
            MAX_RETRIES          = 1
            retry_success        = 0
            retry_failed         = 0
            final_retry_archived = 0

            for retry_num in range(1, MAX_RETRIES + 1):
                logger.info(f"=== RETRY {retry_num}/{MAX_RETRIES} ===")

                exception_files = [f for f in os.listdir(exception_folder) if f.lower().endswith(".pdf")]
                if not exception_files:
                    logger.info("Exception folder empty — stopping retries")
                    break

                total_exceptions = len(exception_files)

                for ex_idx, file_name in enumerate(exception_files, 1):
                    pdf_path        = os.path.join(exception_folder, file_name)
                    lan_id          = "Unknown"
                    page_start_time = time.time()

                    try:
                        lan_id = extract_lan_id_from_filename(file_name)

                        with transaction.atomic():
                            try:
                                file_record = FileRecord.objects.get(lan_id=lan_id)
                            except FileRecord.DoesNotExist:
                                logger.error(f"No FileRecord for LAN_ID: {lan_id}. Skipping retry.")
                                continue
                            except FileRecord.MultipleObjectsReturned:
                                file_record = FileRecord.objects.filter(lan_id=lan_id).first()
                                logger.warning(f"Multiple FileRecords for LAN_ID: {lan_id}. Using ID: {file_record.id}")

                            extracted_data, page_number = process_single_pdf(
                                pdf_path, file_name, file_record, is_retry=True
                            )

                            if extracted_data is None:
                                raise Exception("process_single_pdf returned None on retry")

                            if has_blank_values(extracted_data):
                                if retry_num == MAX_RETRIES:
                                    save_to_page_data_and_cleanup(
                                        file_record, page_number, extracted_data,
                                        file_name, pdf_path,
                                        source_label=f"(final retry {retry_num}, blanks remain)"
                                    )
                                    final_retry_archived += 1
                                else:
                                    save_to_exception(
                                        file_record, page_number, extracted_data,
                                        file_name, pdf_path,
                                        from_exception_folder=True
                                    )
                                    retry_failed += 1
                            else:
                                save_to_page_data_and_cleanup(
                                    file_record, page_number, extracted_data,
                                    file_name, pdf_path,
                                    source_label=f"(retry {retry_num} success)"
                                )
                                retry_success += 1

                        page_elapsed = int(time.time() - page_start_time)
                        self.stdout.write(f"  Retry {retry_num} {ex_idx}/{total_exceptions}: {lan_id} {page_elapsed}s")

                    except Exception as e:
                        logger.error(f"Retry {retry_num} failed for {file_name}: {e}")
                        retry_failed += 1
                        page_elapsed = int(time.time() - page_start_time)
                        self.stdout.write(f"  Retry {retry_num} {ex_idx}/{total_exceptions}: {lan_id} ERROR {page_elapsed}s")

                logger.info(f"Retry {retry_num} done — Success: {retry_success}, Final archived: {final_retry_archived}, Still in exception: {retry_failed}")

            # ─────────────────────────────────────
            # SUMMARY
            # ─────────────────────────────────────
            total_elapsed  = time.time() - total_start_time
            minutes        = int(total_elapsed // 60)
            seconds        = int(total_elapsed % 60)
            total_archived = processed_count + retry_success + final_retry_archived

            self.stdout.write(f"\n  First pass archived  : {processed_count}")
            self.stdout.write(f"  Retry archived       : {retry_success}")
            self.stdout.write(f"  Final retry archived : {final_retry_archived}")
            self.stdout.write(f"  Total archived       : {total_archived}")
            self.stdout.write(f"  Total time           : {minutes}m {seconds}s")

            logger.info(f"Page7 complete. Total archived: {total_archived}, Time: {minutes}m {seconds}s")

        except Exception as e:
            logger.error(f"Main block error: {e}")
            self.stdout.write(self.style.ERROR(f"Error: {e}"))










