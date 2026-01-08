/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
// 1. สำหรับไฟล์ในแอป teacher (เช่น review_submission.html)
        '../../teacher/templates/**/*.html',
        
        // 2. สำหรับไฟล์ในแอป room และ student
        '../../room/templates/**/*.html',
        '../../student/templates/**/*.html',
        
        // 3. สำหรับไฟล์ใน templates หลัก (base.html)
        '../../templates/**/*.html',
        
        // 4. สำหรับไฟล์ในแอป theme เอง
        '../templates/**/*.html',

        // 5. ดักทุกที่เผื่อพิมพ์ผิด
        '../../**/templates/**/*.html',
    ],
    theme: {
        extend: {},
    },
    plugins: [
        require('@tailwindcss/forms'),
        require('@tailwindcss/typography'),
        require('@tailwindcss/aspect-ratio'),
        require("daisyui"),
    ],
    daisyui: {
        themes: [
            {
                mytheme: {
                    "primary": "#5651FF",
                    "secondary": "#FF7E00",
                    "accent": "#FFB01D",
                    "neutral": "#1A1A1A",
                    "base-100": "#FFFFFF",
                    "base-200": "#F5F5F5",
                    "info": "#3ABFF8",
                    "success": "#00964F",
                    "warning": "#FFB01D",
                    "error": "#D3302F",
                },
            },
        ],
    },
}