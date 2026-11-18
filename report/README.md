# report/ — bản LaTeX của bài báo

## Biên dịch

Cần MiKTeX (hoặc TeX Live) và Perl (latexmk cần Perl; Git for Windows đã có sẵn).

```powershell
cd report
latexmk main.tex        # XeLaTeX + BibTeX, PDF ra build/main.pdf
latexmk -c              # dọn file phụ
```

Trong VS Code: cài extension **LaTeX Workshop** (`James-Yu.latex-workshop`). Extension tự đọc `latexmkrc`, lưu file là biên dịch lại.

## Cấu trúc

| Đường dẫn | Nội dung |
|---|---|
| `main.tex` | Preamble (XeLaTeX, Times New Roman, tiếng Việt) và thứ tự các mục |
| `notation.tex` | Bảng ký hiệu dùng chung |
| `sections/` | Mỗi mục một file; dàn ý viết dưới dạng chú thích `%` |
| `generated/` | **Do script sinh**: `numbers.tex` (macro số liệu), `table_*.tex`. Không sửa tay |
| `figures/` | Hình (PDF/PNG), tự vẽ hoặc sinh từ script |
| `refs.bib` | Tài liệu tham khảo; xác minh từng mục trước khi nộp |
| `notes/so_bang_chung.md` | Sổ bằng chứng, bảng chuyển mã, thuật ngữ |

## Quy ước

- Không gõ tay số liệu vào `sections/`; dùng macro trong `generated/numbers.tex`.
- `\todo{...}` hiện chữ đỏ `[CẦN BỔ SUNG: ...]`; xoá hết trước khi nộp.
- Thứ tự viết: bảng chính → Thiết lập → Phương pháp → Kết quả → Phân tích → Thảo luận, Hạn chế → Công trình liên quan → Giới thiệu, Kết luận → Tóm tắt, tiêu đề.
