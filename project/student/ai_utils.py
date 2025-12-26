import os
import json
import mimetypes
import requests
import google.generativeai as genai
from django.conf import settings
import re
from google.api_core import retry
from .ai_schemas import AiMultiFeedback, QuizSchema
import ast
from room.utils import get_active_model


try:
    from markdown import markdown as md_to_html
except Exception:
    md_to_html = None

def check_colab_link_accessibility(url):
    """
    ฟังก์ชันช่วยเช็ค:
    1. รูปแบบ URL ถูกต้อง
    2. Domain คือ colab.research.google.com เป๊ะๆ
    3. ลิงก์เปิดได้จริง (Public) ไม่ติด Login
    """
    # 1. เช็ค Domain แบบเข้มงวด
    try:
        parsed = urlparse(url)
        # ตรวจว่าต้องเป็น https และ domain ต้องเป๊ะ
        if parsed.scheme != "https" or parsed.netloc != "colab.research.google.com":
            return False, "ลิงก์ต้องขึ้นต้นด้วย https://colab.research.google.com/ เท่านั้น"
    except Exception:
        return False, "รูปแบบ URL ไม่ถูกต้อง"

    # 2. ยิง Request ไปเช็คว่าลิงก์เปิดได้ไหม (Ping)
    try:
        # ใส่ User-Agent เพื่อไม่ให้ Google บล็อกว่าเราเป็นบอท
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        # timeout=5 คือถ้าเกิน 5 วิให้ตัดจบ (กันเว็บค้าง)
        response = requests.get(url, headers=headers, timeout=5)

        # ถ้า Google Redirect ไปหน้า Login (accounts.google.com) แสดงว่าไม่ได้เปิดแชร์
        if "accounts.google.com" in response.url or "signin" in response.url:
            return False, "ลิงก์นี้เป็นส่วนตัว (Private) กรุณาเปิดแชร์เป็น 'Anyone with the link' (ทุกคนที่มีลิงก์)"
        
        # ถ้า Response ไม่ใช่ 200 OK
        if response.status_code != 200:
            return False, f"ไม่สามารถเข้าถึงลิงก์ได้ (Status: {response.status_code})"
            
    except requests.exceptions.RequestException:
        return False, "ไม่สามารถเชื่อมต่อกับลิงก์ได้ (ลิงก์อาจเสียหรือหมดอายุ)"

    return True, ""


def validate_file_content(uploaded_file):
    """
    ฟังก์ชันเปิดอ่านเนื้อหาไฟล์เพื่อเช็คว่าเป็น .py หรือ .ipynb ของจริงหรือไม่
    """
    filename = uploaded_file.name.lower()
    
    try:
        # อ่านไฟล์ทั้งหมดขึ้นมาใน Memory เพื่อตรวจสอบ
        content = uploaded_file.read()
        
        # ⚠️ สำคัญมาก: อ่านเสร็จต้องเลื่อน cursor กลับไปที่จุดเริ่มต้น (0) 
        # ไม่งั้นตอน save ลง database ไฟล์จะกลายเป็นไฟล์เปล่า
        uploaded_file.seek(0)
        
        # --- กรณีเป็น .ipynb (ต้องเป็น JSON และมีคีย์ 'cells') ---
        if filename.endswith('.ipynb'):
            try:
                # ลองแปลง bytes เป็น string แล้วโหลด JSON
                data = json.loads(content.decode('utf-8'))
                
                # เช็คโครงสร้างพื้นฐานของ Notebook
                if 'cells' not in data or 'metadata' not in data:
                    return False, "ไฟล์ .ipynb เสียหาย หรือโครงสร้างไม่ถูกต้อง"
            except (json.JSONDecodeError, UnicodeDecodeError):
                return False, "ไม่ใช่ไฟล์ Jupyter Notebook ที่ถูกต้อง (อาจเป็นไฟล์อื่นเปลี่ยนนามสกุลมา)"

        # --- กรณีเป็น .py (ต้องเป็น Text ที่ Compile เป็น Python ได้) ---
        elif filename.endswith('.py'):
            try:
                source_code = content.decode('utf-8')
                # ลอง parse ดูว่าเป็น Python Syntax หรือไม่
                ast.parse(source_code)
            except UnicodeDecodeError:
                return False, "ไฟล์นี้ไม่ใช่ Text File (อาจเป็น Binary/Image เปลี่ยนชื่อมา)"
            except SyntaxError:
                # ถ้า Parse ไม่ผ่าน แปลว่า Syntax ผิด แต่ก็ยังถือว่าเป็น Text File ได้ 
                # แต่ถ้าจะเอาชัวร์ว่าส่งโค้ดรันได้ ให้ return False ตรงนี้ได้เลย
                # ในที่นี้ขออนุญาตปล่อยผ่านกรณี Syntax Error (เผื่อเด็กเขียนโค้ดผิดแต่ส่งไฟล์ถูกประเภท)
                pass 
                
    except Exception as e:
        return False, f"เกิดข้อผิดพลาดในการอ่านไฟล์: {str(e)}"

    return True, ""

def extract_code_from_colab(colab_url):
    """
    ดึง Source Code จาก Colab และคืนค่าเป็น LIST ของ Strings (แยกตาม Cell)
    """
    # 1. ดึง File ID (เหมือนเดิม)
    match = re.search(r'/drive/([a-zA-Z0-9-_]+)', colab_url)
    if not match:
        raise Exception("รูปแบบลิงก์ไม่ถูกต้อง ต้องเป็น /drive/...")
    file_id = match.group(1)
    
    # 2. ดาวน์โหลด JSON (เหมือนเดิม)
    download_url = f'https://drive.google.com/uc?id={file_id}&export=download'
    response = requests.get(download_url)
    if response.status_code != 200:
        raise Exception("ไม่สามารถดาวน์โหลดไฟล์ได้ (เช็คสิทธิ์ Share: Anyone with the link)")

    # 3. ✅ แกะ Code แยกเป็น List
    try:
        notebook_json = response.json()
        code_cells = []
        
        cell_index = 1
        for cell in notebook_json.get('cells', []):
            if cell.get('cell_type') == 'code':
                source_lines = cell.get('source', [])
                if source_lines: # ถ้า Cell ไม่ว่าง
                    source_code = "".join(source_lines)
                    # เก็บเป็น Tuple หรือ Dict ก็ได้ แต่นี่ส่งเป็น Text พร้อม Header เลยง่ายดี
                    code_cells.append(f"--- Cell {cell_index} ---\n{source_code}")
                    cell_index += 1
                    
        return code_cells # 👈 คืนค่าเป็น List of Strings

    except Exception as e:
        raise Exception(f"Parsing Error: {e}")

def call_gemini_structured(prompt_parts_list, pydantic_schema_class):
    """
    เรียก Gemini API (Multimodal) ในโหมด Structured Output
    ✅ อัปเดต: เรียก get_active_model() ภายในฟังก์ชัน เพื่อให้ได้ Config ล่าสุดเสมอ
    """
    print("\n--- ⏳ กำลังส่งคำสั่ง (Multimodal/Structured) ให้ Gemini ---")
    
    # -----------------------------------------------------------------
    # ✅ 1. เรียก Model ล่าสุดจาก Database ที่นี่ (แทน Global Variable)
    # -----------------------------------------------------------------
    model = get_active_model()

    if model is None:
        print("🚨 (CALL_GEMINI) ไม่สามารถโหลด Model ได้ (ตรวจสอบ Admin Config)")
        return None
        
    try:
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=pydantic_schema_class
        )
        
        # -----------------------------------------------------------------
        # ✅ 2. สั่ง Generate (ใช้ 'contents' ตามที่คุณแก้ไขมาถูกต้องแล้ว)
        # -----------------------------------------------------------------
        response = model.generate_content(
            contents=prompt_parts_list, 
            generation_config=generation_config,
            request_options={'retry': retry.Retry(deadline=120)} 
        )
        
        print("✅ Gemini ตอบกลับ (Multimodal/Structured) สำเร็จ")
        return response.text
        
    except Exception as e:
        print(f"🚨 เกิดข้อผิดพลาดในการเรียก Gemini (Multimodal/Structured): {e}")
        return None

def evaluate_submission_with_ai(submission):
    assignment = submission.assignment
    max_score = assignment.score
    
    # ตัวแปรเก็บชิ้นส่วน Prompt
    prompt_parts = []
    student_code_parts = []
    
    # =========================================================
    # 1. แยกแยะประเภทการส่ง (URL vs File) เพื่อเลือก Prompt
    # =========================================================
    
    is_colab = False
    
    # --- กรณี A: Google Colab (URL) ---
    if submission.submission_type.identifier == 'URL' and submission.submitted_link:
        is_colab = True
        print(f"--- 🤖 Mode: Colab Check ({submission.submitted_link}) ---")
        
        # 1.1 ดึง Code
        code_cells = extract_code_from_colab(submission.submitted_link)
        if not code_cells:
            return 0, "ไม่พบ Code ในลิงก์ Colab (หรือลิงก์มีปัญหา)"
            
        student_code_parts.append("\n--- Student's Code (From Google Colab) ---")
        for i, cell_content in enumerate(code_cells):
            student_code_parts.append(f"\n[CELL {i+1}]\n{cell_content}\n[END CELL]")

        # 1.2 ใช้ Prompt แบบ Colab (ตามที่คุณขอ)
        prompt_parts.append(
            "คุณคือผู้ช่วยสอน Python "
            "งานของคุณคือตรวจ 'Google Colab Notebook' ซึ่งประกอบด้วย Code หลาย Cell "
            "เทียบกับ 'โจทย์' ซึ่งมีหลายข้อ\n\n"
            "คำสั่ง:\n"
            "1. วิเคราะห์ Code ในแต่ละ Cell ว่าตรงกับโจทย์ข้อไหน\n"
            "2. ประเมินผลแยกเป็นรายข้อ (ให้ระบุ file_name เป็น 'ข้อที่ 1', 'ข้อที่ 2' เป็นต้น)\n"
            "3. ประเมินผลและให้คะแนนย่อย_เต็ม 10_ (partial_score) และ Feedback ของแต่ละข้อ\n"
            f"4. ให้คะแนนรวม (total_score) โดยอิงจากคะแนนเต็ม {max_score} คะแนน\n" 
            "5. ให้สรุปภาพรวมสั้นๆ (overall_summary) ในตอนท้าย"
        )

    # --- กรณี B: Upload Files ---
    else:
        print("--- 🤖 Mode: File Check ---")
        
        # 1.1 ดึง Code
        files = submission.files.all()
        if not files:
            return 0, "ไม่พบไฟล์งานในระบบ"
        
        student_code_parts.append("\n--- Student's Code (From Uploaded Files) ---")
        for f in files:
            try:
                f.file.seek(0)
                content = f.file.read().decode('utf-8', errors='replace')
                name = os.path.basename(f.file.name)
                student_code_parts.append(f"\n[FILE: {name}]\n{content}\n[END FILE]")
            except Exception:
                student_code_parts.append(f"\n[ERROR Reading {f.file.name}]")

        # 1.2 ใช้ Prompt แบบ File (ตามที่คุณขอ)
        prompt_parts.append(
            "คุณคือผู้ช่วยสอน (TA) ผู้เชี่ยวชาญ Python "
            "งานของคุณคือตรวจ 'โค้ดของนักเรียน' (ซึ่งอาจมีหลายไฟล์) เทียบกับ 'โจทย์' (ซึ่งอาจมีหลายข้อ) "
            "โจทย์อาจจะมาจาก 'คำอธิบาย (Text)', 'ไฟล์โจทย์ (PDF/Image)', หรือ 'ไฟล์ Test Case (เสริม)' "
            "คำสั่ง:\n"
            "1. ประเมินผลและให้คะแนนย่อย_เต็ม 10_ (partial_score) สำหรับโค้ดแต่ละไฟล์\n"
            f"2. ให้คะแนนรวม (total_score) โดยอิงจากคะแนนเต็ม {max_score} คะแนน (ห้ามเกิน)\n"
            "3. ให้สรุปภาพรวมสั้นๆ (overall_summary) ของงานทั้งหมดด้วย"
        )

    # =========================================================
    # 2. เพิ่มคำสั่งระบบ (System Instructions) เพื่อให้ Code ไม่พัง
    # =========================================================
    # จำเป็นต้องใส่ต่อท้าย เพื่อบังคับ Output JSON และภาษาไทย
    prompt_parts.append(
        "\n\n🚨 SYSTEM REQUIREMENTS (Do not ignore):\n"
        "- **Return output as JSON** matching the schema provided.\n"
        "- **Language:** You MUST answer in **THAI (ภาษาไทย)** only.\n"
        "- **Scoring:** Ensure `total_score` does not exceed the max score.\n"
    )
    
    if is_colab:
        prompt_parts.append("- **Colab Mapping:** Map logic in cells to questions. Use 'ข้อที่ 1', 'ข้อที่ 2' as `file_name` in JSON.\n")
    else:
        prompt_parts.append("- **File Mapping:** Use the actual filename as `file_name` in JSON.\n")

    # =========================================================
    # 3. ใส่ข้อมูลโจทย์ (เหมือนเดิม)
    # =========================================================
    if assignment.description:
        prompt_parts.append(f"\n--- Assignment Description ---\n{assignment.description}")

    if assignment.problem_file:
        try:
            assignment.problem_file.file.seek(0)
            file_bytes = assignment.problem_file.file.read()
            mime_type = mimetypes.guess_type(assignment.problem_file.name)[0]
            if mime_type in ["application/pdf", "image/png", "image/jpeg"]:
                prompt_parts.append(f"\n--- Assignment File ({mime_type}) ---")
                prompt_parts.append({"mime_type": mime_type, "data": file_bytes})
        except Exception as e:
            print(f"Error reading problem file: {e}")

    if assignment.test_case_file:
        try:
            assignment.test_case_file.file.seek(0)
            test_data = assignment.test_case_file.file.read().decode('utf-8', errors='replace')
            prompt_parts.append(f"\n--- Test Cases ---\n{test_data}")
        except Exception:
            pass

    # =========================================================
    # 4. ใส่ Code ของนักเรียน (ที่เตรียมไว้ข้างบน)
    # =========================================================
    prompt_parts.extend(student_code_parts)

    # =========================================================
    # 5. ส่งให้ AI และ ประมวลผลผลลัพธ์
    # =========================================================
    print("--- ⏳ Sending to Gemini... ---")
    raw_response = call_gemini_structured(prompt_parts, AiMultiFeedback)
    
    if not raw_response:
        return 0, "เกิดข้อผิดพลาด: AI ไม่ตอบสนอง"

    try:
        data = json.loads(raw_response)
        
        total_score = data.get('total_score', 0)
        summary = data.get('overall_summary', '')
        feedbacks = data.get('feedbacks', [])

        # สร้าง Report
        report_lines = []
        if summary:
            report_lines.append(f"📝 **สรุปภาพรวม:** {summary}")
            report_lines.append("=" * 40 + "\n")

        if not feedbacks:
            report_lines.append("⚠️ AI ไม่ได้แยกรายละเอียดรายข้อมาให้")
        else:
            for fb in feedbacks:
                fname = fb.get('file_name', 'Unknown')
                fscore = fb.get('partial_score', 0)
                ftext = fb.get('feedback_text', '-').replace('\n', '\n  ')
                
                report_lines.append(
                    f"📌 **{fname}** (คะแนน: {fscore}/10)\n"
                    f"  {ftext}\n"
                    f"{'-' * 40}"
                )
        
        final_feedback_text = "\n".join(report_lines)

        # แปลง Markdown -> HTML (ถ้ามีไลบรารี markdown) หากไม่มีก็แปลงเป็น <br/> เป็น fallback
        if md_to_html:
            final_feedback_html = md_to_html(final_feedback_text)
        else:
            final_feedback_html = final_feedback_text.replace('\n', '<br/>')

        return total_score, final_feedback_html

    except Exception as e:
        print(f"Processing Error: {e}")
        return 0, f"เกิดข้อผิดพลาดในการประมวลผล: {e}"
    
def generate_quiz_with_ai(submission,num_questions, num_choices):
    assignment = submission.assignment
    student_code_parts = []
    
    # 1. เตรียม Prompt
    prompt_parts = [
        "You are a Computer Science Teacher.",
        "Create a specialized quiz based on the student's code and the assignment description.",
        "The quiz should test if the student truly understands their own code and the concepts used.",
        "\n🔴 REQUIREMENTS:",
        
        # ✅ แก้ตรงนี้: เอาตัวแปรมาใส่แทนเลข 5 และ 4
        f"1. Create exactly {num_questions} Multiple Choice Questions.",
        f"2. Each question must have {num_choices} choices.",
        
        "3. Only ONE choice is correct per question.",
        "4. Return strictly in JSON format matching the schema.",
        "5. Language: THAI (ภาษาไทย).",
    ]
    
    # --- 1.1 ใส่คำอธิบายโจทย์ (Text) ---
    if assignment.description:
        prompt_parts.append(f"\n--- Assignment Description ---\n{assignment.description}")

    # --- 1.2 ✅ เพิ่มส่วนนี้: ใส่ไฟล์โจทย์ (PDF/Image) ---
    if assignment.problem_file:
        try:
            assignment.problem_file.file.seek(0)
            file_bytes = assignment.problem_file.file.read()
            mime_type = mimetypes.guess_type(assignment.problem_file.name)[0]
            
            # ตรวจสอบว่าเป็นไฟล์ที่ AI อ่านได้หรือไม่
            if mime_type in ["application/pdf", "image/png", "image/jpeg", "image/webp"]:
                print(f"--- 📎 แนบไฟล์โจทย์: {mime_type} ---")
                prompt_parts.append(f"\n--- Assignment File ({mime_type}) ---")
                prompt_parts.append({
                    "mime_type": mime_type,
                    "data": file_bytes
                })
        except Exception as e:
            print(f"Error reading assignment file: {e}")

    # --- 2. เตรียม Code นักเรียน ---
    
    # กรณี A: Colab Link
    if submission.submission_type.identifier == 'URL' and submission.submitted_link:
        print(f"--- 🤖 Mode: Colab Check ({submission.submitted_link}) ---")
        
        code_cells = extract_code_from_colab(submission.submitted_link)
        if not code_cells:
            # ถ้าอ่าน Colab ไม่ได้ อาจจะ Return Error หรือปล่อยให้ AI สร้างจากโจทย์อย่างเดียว
            print("Warning: ไม่พบ Code ใน Colab")
            
        student_code_parts.append("\n--- Student's Code (From Google Colab) ---")
        for i, cell_content in enumerate(code_cells):
            student_code_parts.append(f"\n[CELL {i+1}]\n{cell_content}\n[END CELL]")
            
    # กรณี B: File Upload (แก้ Indentation ให้ถูกต้อง)
    else: 
        print("--- 🤖 Mode: File Check ---")
        files = submission.files.all()
        
        student_code_parts.append("\n--- Student's Code (From Uploaded Files) ---")
        if not files:
            print("Warning: ไม่พบไฟล์งาน")
            
        for f in files:
            try:
                f.file.seek(0)
                content = f.file.read().decode('utf-8', errors='replace')
                name = os.path.basename(f.file.name)
                student_code_parts.append(f"\n[FILE: {name}]\n{content}\n[END FILE]")
            except Exception:
                student_code_parts.append(f"\n[ERROR Reading {f.file.name}]")

    # --- 3. ✅ สำคัญมาก: เอา Code นักเรียนใส่เข้าไปใน Prompt รวม ---
    prompt_parts.extend(student_code_parts)

    # 4. เรียก AI
    print("--- 🎲 Generating Quiz with AI ---")
    
    # ส่ง Schema QuizSchema ไปด้วย (ต้องแน่ใจว่า import มาแล้ว)
    raw_response = call_gemini_structured(prompt_parts, QuizSchema)
    
    if not raw_response:
        return None

    try:
        data = json.loads(raw_response)
        return data.get('questions', []) 
    except Exception as e:
        print(f"Quiz GenError: {e}")
        return None