import time
import json
import os
import google.generativeai as genai
from django.core.management.base import BaseCommand
from room.models import Submission
from student.ai_utils import extract_code_from_colab  # ตรวจ path ให้ตรง

# --- ⚙️ ตั้งค่าราคา (อิงตามภาพ Gemini 2.5 Flash Paid Tier) ---
# Input: $0.30 per 1M tokens
# Output: $2.50 per 1M tokens
PRICE_PER_1M_INPUT_USD = 0.30
PRICE_PER_1M_OUTPUT_USD = 2.50
EXCHANGE_RATE = 34.0  # 1 USD = 34 THB โดยประมาณ

class Command(BaseCommand):
    help = 'Benchmark speed, cost, and limits of Gemini 2.5 Flash'

    def add_arguments(self, parser):
        parser.add_argument('submission_id', type=int, help='ID of the submission to test')

    def handle(self, *args, **options):
        sub_id = options['submission_id']
        
        try:
            submission = Submission.objects.get(id=sub_id)
        except Submission.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Submission ID {sub_id} not found'))
            return

        self.stdout.write(self.style.WARNING(f'\n🚀 Starting Benchmark (Gemini 2.5 Flash) for Submission ID: {sub_id}'))
        
        # 🧪 Scenarios: เพิ่ม 100 ข้อ เพื่อเทส Limit ของ Output Tokens
        scenarios = [10, 20, 50, 100] 
        results = []
        
        # ตั้งค่า API
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        
        # ✅ ใช้โมเดลตามภาพ
        model_name = 'gemini-2.5-flash' 
        model = genai.GenerativeModel(model_name)

        self.stdout.write(f"Model: {model_name}")
        self.stdout.write(f"Pricing: Input ${PRICE_PER_1M_INPUT_USD}/1M | Output ${PRICE_PER_1M_OUTPUT_USD}/1M")

        for q_num in scenarios:
            self.stdout.write(f"\n--- 🧪 Testing: {q_num} Questions ---")
            
            # 1. เตรียม Prompt
            prompt_parts = self.build_prompt(submission, q_num)
            
            # 2. เริ่มจับเวลา
            start_time = time.time()
            try:
                # สร้าง Config
                # หมายเหตุ: Gemini รุ่นใหม่ๆ มักมี Output limit สูงขึ้น (8k+)
                # 100 ข้อน่าจะรอด แต่อาจจะใช้เวลานานหน่อย
                generation_config = genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.7
                )

                response = model.generate_content(
                    prompt_parts,
                    generation_config=generation_config
                )
                
                # Trigger การดึง text
                response_text = response.text 
                
                # ลอง Parse JSON เพื่อเช็คความสมบูรณ์
                try:
                    json.loads(response_text)
                    is_valid_json = "✅ OK"
                except json.JSONDecodeError:
                    is_valid_json = "⚠️ Invalid JSON (Cut off?)"

                end_time = time.time()
                duration = end_time - start_time
                
                # 3. ดึง Usage Metadata
                usage = response.usage_metadata
                in_tok = usage.prompt_token_count
                out_tok = usage.candidates_token_count
                
                # 4. คำนวณราคา (บาท)
                cost_usd = ((in_tok / 1_000_000) * PRICE_PER_1M_INPUT_USD) + \
                           ((out_tok / 1_000_000) * PRICE_PER_1M_OUTPUT_USD)
                cost_thb = cost_usd * EXCHANGE_RATE
                
                results.append({
                    "q": q_num,
                    "time": duration,
                    "in": in_tok,
                    "out": out_tok,
                    "cost": cost_thb,
                    "status": is_valid_json
                })
                self.stdout.write(self.style.SUCCESS(f"Done in {duration:.2f}s | Output: {out_tok} tokens"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Fail at {q_num} items: {e}"))
                results.append({"q": q_num, "status": "❌ Fail", "time": 0, "in":0, "out":0, "cost":0})
                
            # พัก 3 วินาที (รุ่นใหม่อาจจะมี Rate Limit เข้มงวดขึ้นนิดหน่อย)
            time.sleep(3)

        # --- 5. สรุปผลตาราง ---
        self.print_table(results)

    def build_prompt(self, submission, num_questions):
        # ... (ใช้ Logic เดิมได้เลยครับ) ...
        assignment = submission.assignment
        prompt_parts = [
            f"Create a specialized quiz with exactly {num_questions} questions based on the student code.",
            "Format: JSON list of objects {question, options[], answer, explanation}",
            "Language: Thai",
            "Difficulty: Mixed"
        ]
        
        if assignment.description:
             prompt_parts.append(f"Assignment Description: {assignment.description}")
        
        student_code = ""
        # ส่วนดึงโค้ด
        if submission.submission_type and submission.submission_type.identifier == 'URL' and submission.submitted_link:
             try:
                cells = extract_code_from_colab(submission.submitted_link)
                if cells: student_code = "\n".join(cells)
             except Exception as e:
                 student_code = f"Error loading code: {e}"
        else:
             for f in submission.files.all():
                 try:
                    f.file.seek(0)
                    student_code += f"\nFile: {f.file.read().decode('utf-8', errors='ignore')}"
                 except: pass
        
        prompt_parts.append(f"Student Code:\n{student_code}")
        return prompt_parts

    def print_table(self, results):
        self.stdout.write("\n" + "="*95)
        self.stdout.write(f"{'Qty':<5} | {'Time(s)':<8} | {'In Tok':<8} | {'Out Tok':<8} | {'Cost(THB)':<10} | {'Status'}")
        self.stdout.write("-" * 95)
        
        for r in results:
            if r['time'] > 0:
                self.stdout.write(f"{r['q']:<5} | {r['time']:<8.2f} | {r['in']:<8} | {r['out']:<8} | {r['cost']:<10.4f} | {r['status']}")
            else:
                self.stdout.write(f"{r['q']:<5} | {'FAILED':<8} | {'-':<8} | {'-':<8} | {'-':<10} | {r['status']}")
        self.stdout.write("="*95 + "\n")