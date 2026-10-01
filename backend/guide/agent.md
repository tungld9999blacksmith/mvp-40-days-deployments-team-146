# Mô tả

## Cách đặt tên:

- Quy tắc: `<vai trò của agent>_agent.py`

- Quy tắc đặt tên file tool.py: Nên là một verb phase ví dụ:
    `search_web.py` hay `get_uer.py`

## Cách tổ chức của một agent

Một thư mục source code agent gồm 3 thư mục chính:

- `tools/`: lưu các tool nội bộ của agent
- `prompt/`: lưu các file prompt, template prompt
- `router/`: Lưu các file router hay là các file chứa Tool-Definition
- `nodes/` (optional): nếu sử dụng graph thì các file source code sẽ lưu tại thư mục này

- `tools/rag/`(optional): Thư mục này chứa source code của method gọi rag hoặc, chưa logic của chunking, indexing, embed 

File `*_agent.py` (hoặc `*_graph.py` nếu sử dụng graph) sẽ được lưu tại thư mục chính của thư mục agent đang định nghĩa

