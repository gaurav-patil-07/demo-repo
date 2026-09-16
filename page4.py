from django.core.management.base import BaseCommand
from mvqc.models import FileRecord, PageData, ExceptionData
import os
import re
import shutil
import pdfplumber  # type: ignore
from datetime import datetime
from django.db import transaction
import logging
import time
import gc


class Command(BaseCommand):
    help = 'Process all PDFs in Page4 folder and extract Sanction Cum Loan Agreement data to database'

    def add_arguments(self, parser):
        parser.add_argument('--folder', type=str, default='Data4',
                            help='Folder to process: Data1, Data2, Data3 or Data4')

    def handle(self, *args, **options):

        # === CONFIG ===
        from django.conf import settings
        folder = options.get('folder') or 'Data4'
        PDFFilePath = os.path.join(settings.BASE_DIR, "output", folder, f"{folder}_Output", "Page4")

        log_folder = os.path.join(settings.BASE_DIR, "mvqc", "logs")
        try:
            os.makedirs(log_folder, exist_ok=True)
        except Exception:
            pass  # Continue without logging if folder creation fails

        today    = datetime.now().strftime('%Y-%m-%d')
        log_file = os.path.join(log_folder, f"page4_{today}.log")

        logger = logging.getLogger('page4')
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

        # ─────────────────────────────────────────
        # HELPERS
        # ─────────────────────────────────────────
        def clean_text(value):
            if isinstance(value, list):
                value = " ".join(str(v) for v in value)
            if isinstance(value, str):
                value = value.replace("\\n", " ").replace("\r", " ")
                value = " ".join(value.split())
            return value.strip() if value else ""

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
                return int(match.group(1)) if match else 4
            except:
                return 4

        def extract_lan_id_from_filename(file_name):
            filename_no_ext = os.path.splitext(file_name)[0]
            parts = filename_no_ext.split("_")
            if parts[0].lower().startswith("page"):
                return parts[1] if len(parts) > 1 else ""
            return parts[0] if parts else ""

        def safe_move_file(src, dst, max_retries=3, delay=0.5):
            """Move file with retry logic to handle file locking issues."""
            for attempt in range(max_retries):
                try:
                    gc.collect()  # Force garbage collection to release file handles
                    time.sleep(delay)  # Small delay to ensure file is released
                    shutil.move(src, dst)
                    return True
                except PermissionError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"File locked, retrying move ({attempt + 1}/{max_retries}): {os.path.basename(src)}")
                        time.sleep(delay * (attempt + 1))  # Increasing delay
                    else:
                        logger.error(f"Failed to move file after {max_retries} attempts: {os.path.basename(src)} - {e}")
                        return False
                except Exception as e:
                    logger.error(f"Error moving file {os.path.basename(src)}: {e}")
                    return False
            return False

        def extract_tables_to_string(pdf_path):
            output = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    if tables is not None:
                        for table in tables:
                            if table is None:
                                continue
                            for row in table:
                                output.append(f"{row}\n")
                            output.append("\n")
            return ''.join(output)

        def extract_amount(section_text, label):
            if not section_text:
                return ""
            normalized_text = section_text.replace('\u2013', '-').replace('\u2014', '-').replace('\x96', '-')
            # Try pattern with dashes first
            pattern = rf"{label}\s*[-]+\s*Rs\.?\s*(NA|N/?A|NIL|[0-9][0-9,.\-]*)\b"
            match = re.search(pattern, normalized_text, re.IGNORECASE)
            if match:
                return clean_text(match.group(1))
            # Fallback: try without requiring dashes
            pattern_no_dash = rf"{label}\s*Rs\.?\s*(NA|N/?A|NIL|[0-9][0-9,.\-]*)\b"
            match = re.search(pattern_no_dash, normalized_text, re.IGNORECASE)
            if match:
                return clean_text(match.group(1))
            return ""

        def is_na_value(value):
            if not value:
                return True
            normalized = value.strip().upper()
            return normalized in {"NA", "N/A", "NIL"}

        def extract_agreement_date(full_text):
            if not full_text:
                return ""
            text = " ".join(full_text.split())
            # Primary pattern: ISO datetime
            m = re.search(
                r"Date of Agreement\s*[':-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})(?:\s+[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.\d+)?)?",
                text, re.IGNORECASE
            )
            if m:
                try:
                    return datetime.strptime(m.group(1), "%Y-%m-%d").strftime("%d-%m-%Y")
                except Exception:
                    pass
            # dd/mm/yyyy
            m = re.search(r"Date of Agreement\s*[':-]?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", text, re.IGNORECASE)
            if m:
                try:
                    return datetime.strptime(m.group(1), "%d/%m/%Y").strftime("%d-%m-%Y")
                except Exception:
                    pass
            # Month name d, yyyy
            m = re.search(
                r"Date of Agreement\s*[':-]?\s*([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})",
                text, re.IGNORECASE
            )
            if m:
                for fmt in ("%B %d, %Y", "%b %d, %Y"):
                    try:
                        return datetime.strptime(m.group(1), fmt).strftime("%d-%m-%Y")
                    except Exception:
                        continue
            # Fallback: scan list-like row
            try:
                for line in full_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                    if "Date of Agreement" in line:
                        parts = line.split("'")
                        for i, token in enumerate(parts):
                            if "Date of Agreement" in token and i + 2 < len(parts):
                                candidate = parts[i + 2].strip().split(" ")[0]
                                if re.match(r"^\d{4}-\d{2}-\d{2}$", candidate):
                                    return datetime.strptime(candidate, "%Y-%m-%d").strftime("%d-%m-%Y")
                                if re.match(r"^\d{2}/\d{2}/\d{4}$", candidate):
                                    return datetime.strptime(candidate, "%d/%m/%Y").strftime("%d-%m-%Y")
                                return candidate
            except Exception:
                pass
            return ""

        def save_to_page_data_and_cleanup(file_record, page_number, extracted_data, file_name, pdf_path, source_label=""):
            """Save to PageData, delete ExceptionData, move file to archive."""
            PageData.objects.update_or_create(
                pdf=file_record,
                page_number=page_number,
                defaults={'json_data': extracted_data}
            )
            ExceptionData.objects.filter(pdf=file_record, file=file_name).delete()
            if os.path.exists(pdf_path):
                safe_move_file(pdf_path, os.path.join(archive_folder, file_name))
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
                    safe_move_file(pdf_path, os.path.join(exception_folder, file_name))
            logger.info(f"{file_name}: Saved to ExceptionData {'(updated)' if not ex_created else '(created)'}")

        # ─────────────────────────────────────────
        # CORE EXTRACTION
        # ─────────────────────────────────────────
        def process_single_pdf(pdf_path, file_name, file_record, is_retry=False):
            try:
                lan_id      = extract_lan_id_from_filename(file_name)
                page_number = extract_page_number(os.path.splitext(file_name)[0])

                headers = [
                    "LAN_ID", "Loan_Purpose", "Name", "Email_Address", "Full_address",
                    "Mobile_Number", "Original_Amount_with_GST", "Loan_Amount",
                    "Premium_Amount", "Loan_Tenure", "EMI", "Rate", "Closure_Amount",
                    "Disbursement_Amount", "Loan_Amount_SanctionCumLoanAgreement",
                    "Loan_Amount_Without_Insurance_Amount", "Agreement_Date"
                ]
                extracted_data           = {h: "" for h in headers}
                extracted_data["LAN_ID"] = lan_id

                # --- Extract raw table text ---
                OutputData  = extract_tables_to_string(pdf_path)
                OutputData  = OutputData.replace('"', "'").replace("Customer's", "Customers")
                text_lines  = OutputData.replace("\r\n", "\n").replace("\r", "\n").split("\n")

                # --- Agreement Date ---
                extracted_data["Agreement_Date"] = extract_agreement_date(OutputData)

                # --- Line-based fields ---
                def safe_split(line, idx):
                    parts = line.split("'")
                    return clean_text(parts[idx]) if len(parts) > idx else ""

                extracted_data["Loan_Purpose"]             = safe_split(text_lines[1], 7) if len(text_lines) > 1 else ""
                extracted_data["Name"]                     = safe_split(text_lines[2], 3) if len(text_lines) > 2 else ""
                extracted_data["Email_Address"]            = safe_split(text_lines[3], 3) if len(text_lines) > 3 else ""
                extracted_data["Full_address"]             = safe_split(text_lines[4], 3) if len(text_lines) > 4 else ""
                extracted_data["Mobile_Number"]            = safe_split(text_lines[5], 3) if len(text_lines) > 5 else ""
                extracted_data["Original_Amount_with_GST"] = safe_split(text_lines[5], 7) if len(text_lines) > 5 else ""
                extracted_data["Rate"]                     = safe_split(text_lines[6], 7) if len(text_lines) > 6 else ""
                extracted_data["Loan_Tenure"]              = safe_split(text_lines[7], 3) if len(text_lines) > 7 else ""
                extracted_data["EMI"]                      = safe_split(text_lines[7], 7) if len(text_lines) > 7 else ""
                extracted_data["Closure_Amount"]           = safe_split(text_lines[8], 7) if len(text_lines) > 8 else ""
                extracted_data["Disbursement_Amount"]      = safe_split(text_lines[9], 7) if len(text_lines) > 9 else ""

                # --- Amount fields ---
                loan_with_insurance    = extract_amount(OutputData, r"With insurance")
                loan_without_insurance = extract_amount(OutputData, r"Without insurance")
                insurance_premium      = extract_amount(OutputData, r"Insurance Premium\*{0,2}")

                extracted_data["Loan_Amount"]       = loan_with_insurance
                extracted_data["Premium_Amount"]    = insurance_premium

                # if is_na_value(insurance_premium):
                #     extracted_data["Loan_Amount_SanctionCumLoanAgreement"] = loan_without_insurance
                # else:
                #     extracted_data["Loan_Amount_SanctionCumLoanAgreement"] = loan_with_insurance

                if not is_na_value(loan_with_insurance):
                    extracted_data["Loan_Amount_SanctionCumLoanAgreement"] = loan_with_insurance
                elif not is_na_value(loan_without_insurance):
                    extracted_data["Loan_Amount_SanctionCumLoanAgreement"] = loan_without_insurance
                else:
                    extracted_data["Loan_Amount_SanctionCumLoanAgreement"] = insurance_premium
                # Store "Loan Without Insurance" amount
                extracted_data["Loan_Amount_Without_Insurance_Amount"] = loan_without_insurance

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
                import traceback
                error_details = traceback.format_exc()
                logger.error(f"Error processing {file_name}: {e}")
                logger.error(f"Traceback: {error_details}")
                return None, None

        # ─────────────────────────────────────────
        # MAIN
        # ─────────────────────────────────────────
        try:
            total_start_time = time.time()
            self.stdout.write("INFO - Starting Page4 processing...")

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
            all_pdf_files = [f for f in os.listdir(PDFFilePath) if f.endswith(".pdf")]
            pdf_files = [f for f in all_pdf_files if not os.path.exists(os.path.join(archive_folder, f))]
            archived_count = len(all_pdf_files) - len(pdf_files)
            if archived_count > 0:
                logger.info(f"Skipped {archived_count} already archived file(s)")
                self.stdout.write(f"INFO - Skipped {archived_count} already archived file(s)")
            total_files = len(pdf_files)
            logger.info(f"Found {total_files} PDF(s) to process (excluding archived)")

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
                    gc.collect()  # Force release of file handles
                    if os.path.exists(pdf_path):
                        safe_move_file(pdf_path, os.path.join(exception_folder, file_name))
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

                exception_files = [f for f in os.listdir(exception_folder) if f.endswith(".pdf")]
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
                                    # Final retry — save best data, delete exception, archive
                                    save_to_page_data_and_cleanup(
                                        file_record, page_number, extracted_data,
                                        file_name, pdf_path,
                                        source_label=f"(final retry {retry_num}, blanks remain)"
                                    )
                                    final_retry_archived += 1
                                else:
                                    # Not final — update exception, keep in folder
                                    save_to_exception(
                                        file_record, page_number, extracted_data,
                                        file_name, pdf_path,
                                        from_exception_folder=True
                                    )
                                    retry_failed += 1
                            else:
                                # Complete — save, delete exception, archive
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
                        gc.collect()  # Force release of file handles
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

            logger.info(f"Page4 complete. Total archived: {total_archived}, Time: {minutes}m {seconds}s")

        except Exception as e:
            logger.error(f"Main block error: {e}")
            self.stdout.write(self.style.ERROR(f"Error: {e}"))