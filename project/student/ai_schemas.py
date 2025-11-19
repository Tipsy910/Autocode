# --- student/ai_schemas.py ---
# (ไฟล์ใหม่สำหรับเก็บ Pydantic Models ทั้งหมด)

from pydantic import BaseModel, Field
from typing import List, Optional

# --- Model สำหรับ Feedback (แบบแยกไฟล์) ---
class AiFileFeedback(BaseModel):
    file_name: str = Field(description="ชื่อของไฟล์ที่กำลังประเมิน เช่น ex1.py")
    partial_score: int = Field(description="คะแนน (เต็ม 10) ที่ประเมินได้สำหรับ 'ไฟล์นี้ไฟล์เดียว'")
    feedback_text: str = Field(description="ข้อความ Feedback เฉพาะสำหรับ 'ไฟล์นี้ไฟล์เดียว'")

class AiMultiFeedback(BaseModel):
    total_score: int = Field(description="คะแนน 'รวม' ที่ประเมินได้ (Based on assignment max score)")
    overall_summary: str = Field(description="สรุปภาพรวมสั้นๆ ของงานทั้งหมด (Short Overall Feedback)")
    feedbacks: List[AiFileFeedback] = Field(
        description="ลิสต์ของ Feedback โดยประเมินแยกตามแต่ละไฟล์ที่นักเรียนส่งมา"
    )

# --- Model สำหรับ Quiz (เผื่อไว้) ---
class AiChoice(BaseModel):
    choice_text: str = Field(description="ข้อความในตัวเลือก")
    is_correct: bool = Field(description="ตัวเลือกนี้ถูกหรือผิด")

class AiQuestion(BaseModel):
    question_text: str = Field(description="ข้อความคำถาม")
    choices: List[AiChoice] = Field(description="ลิสต์ของตัวเลือก 4 ข้อ")

class AiQuiz(BaseModel):
    questions: List[AiQuestion] = Field(description="ลิสต์ของคำถาม")