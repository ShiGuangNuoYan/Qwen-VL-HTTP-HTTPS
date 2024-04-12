import os
import re
import uuid
import copy
import asyncio
from pathlib import Path
from argparse import ArgumentParser
from typing import Tuple, List, Dict, Union, Optional
import json

from fastapi.param_functions import Body
import aiofiles
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
import uvicorn
import secrets
from modelscope import AutoModelForCausalLM, AutoTokenizer, GenerationConfig
# from KGQA.poem_chat import ChatPoemGraph
# �������뱣�ֲ���


PUNCTUATION = "�����������磥�������������������������������ۣܣݣޣߣ��������?????��������������������������?????����????�C������?����??��?�n."
uploaded_file_dir="save"
DEFAULT_CKPT_PATH = 'qwen/Qwen-VL-Chat'
# ������û���ʷ��¼����
global all_history,all_talk
all_history=[]
all_talk=[]
for i in range(1000):
    all_history.append([])
    all_talk.append([])
#chatbot=ChatPoemGraph()
def _get_args():
    parser = ArgumentParser()
    parser.add_argument("-c", "--checkpoint-path", type=str, default=DEFAULT_CKPT_PATH,
                        help="Checkpoint name or path, default to %(default)r")
    parser.add_argument("--cpu-only", action="store_true", help="Run demo with CPU only")

    parser.add_argument("--share", action="store_true", default=False,
                        help="Create a publicly shareable link for the interface.")
    parser.add_argument("--inbrowser", action="store_true", default=False,
                        help="Automatically launch the interface in a new tab on the default browser.")
    parser.add_argument("--server-port", type=int, default=8000,
                        help="Demo server port.")
    parser.add_argument("--server-name", type=str, default="127.0.0.1",
                        help="Demo server name.")

    args = parser.parse_args()
    return args

def _load_model_tokenizer(args):
    tokenizer = AutoTokenizer.from_pretrained(
        args.checkpoint_path, trust_remote_code=True, resume_download=True, revision='master',
    )

    if args.cpu_only:
        device_map = "cpu"
    else:
        device_map = "cuda"

    model = AutoModelForCausalLM.from_pretrained(
        args.checkpoint_path,
        device_map=device_map,
        trust_remote_code=True,
        resume_download=True,
        revision='master',
    ).eval()
    model.generation_config = GenerationConfig.from_pretrained(
        args.checkpoint_path, trust_remote_code=True, resume_download=True, revision='master',
    )

    return model, tokenizer

args=_get_args()
model, tokenizer = _load_model_tokenizer(args)



def _parse_text(text):
    lines = text.split("\n")
    lines = [line for line in lines if line != ""]
    count = 0
    for i, line in enumerate(lines):
        if "```" in line:
            count += 1
            items = line.split("`")
            if count % 2 == 1:
                lines[i] = f'<pre><code class="language-{items[-1]}">'
            else:
                lines[i] = f"<br></code></pre>"
        else:
            if i > 0:
                if count % 2 == 1:
                    line = line.replace("`", r"\`")
                    line = line.replace("<", "&lt;")
                    line = line.replace(">", "&gt;")
                    line = line.replace(" ", "&nbsp;")
                    line = line.replace("*", "&ast;")
                    line = line.replace("_", "&lowbar;")
                    line = line.replace("-", "&#45;")
                    line = line.replace(".", "&#46;")
                    line = line.replace("!", "&#33;")
                    line = line.replace("(", "&#40;")
                    line = line.replace(")", "&#41;")
                    line = line.replace("$", "&#36;")
                lines[i] = "<br>" + line
    text = "".join(lines)
    return text




async def add_file(history, task_history, file):
    image_filename = file.filename  # ȡ�ϴ��ļ����ļ�����
    received_dirpath = "Qwen-VL/resource"
    if not os.path.isdir(received_dirpath):  # ��������ڸ�·���ͽ�һ��·��
        os.makedirs(received_dirpath)
    imageFilePath = os.path.join(received_dirpath, image_filename)  # �����ϴ��ļ�������·��
    print(imageFilePath)
    #file.save(imageFilePath)  # �����յ����ļ����浽�������ϵ�ָ��·����
    async with aiofiles.open(imageFilePath, 'wb') as out_file:
        content = await file.read()  # ��ȡ�ļ�����
        await out_file.write(content)  # �첽д���ļ�
    history = history + [((imageFilePath,), None)]
    # global all_talk
    # all_talk[user_id]=all_talk[user_id]+[((file.name,), None)]
    # global all_history
    # all_history[user_id]=all_history[user_id]+[((file.name,), None)]
    task_history = task_history + [((imageFilePath,), None)]
    return history, task_history,imageFilePath


def add_text(history, task_history, text):
    task_text = text
    if len(text) >= 2 and text[-1] in PUNCTUATION and text[-2] not in PUNCTUATION:
        task_text = text[:-1]
    history = history + [(text, None)]
    task_history = task_history + [(task_text, None)]
    return history, task_history

def _remove_image_special(text):
    text = text.replace('<ref>', '').replace('</ref>', '')
    return re.sub(r'<box>.*?(</box>|$)', '', text)


app = FastAPI()

async def predict(talk,history,file):
    chat_query=talk[-1][0]
    query=history[-1][0]
    print("User: " + query)
    history_cp = copy.deepcopy(history)
    full_response = ""

    history_filter = []
    pic_idx = 1
    pre = ""
    last_yield_done = False
    for i, (q, a) in enumerate(history_cp):
        if isinstance(q, (tuple, list)):
            q = f'Picture {pic_idx}: <img>{q[0]}</img>'
            pre += q + '\n'
            pic_idx += 1
        else:
            pre += q
            history_filter.append((pre, a))
            pre = ""
    new_history, message = history_filter[:-1], history_filter[-1][0]
    ans=None
    # if not file:
    #     ans=chatbot.chat_main(query)
    #     if ans!=None:
    #         full_response = ans
    #         history.append((message, full_response))
    #         talk[-1] = (chat_query, full_response)
    if file or ans==None:
        for response in model.chat_stream(tokenizer, message, history=new_history):
            # print(response)
            talk[-1] = (chat_query, _remove_image_special(response))
            yield talk[-1][1]
            full_response = response
            last_yield_done=True
        response = full_response
        history.append((message, response))
        # image = tokenizer.draw_bbox_on_latest_picture(response, history)
        image = None
        if image is not None:
            temp_dir = secrets.token_hex(20)
            temp_dir = Path(uploaded_file_dir) / temp_dir
            temp_dir.mkdir(exist_ok=True, parents=True)
            name = f"tmp{secrets.token_hex(5)}.jpg"
            filename = temp_dir / name
            image.save(str(filename))
            talk.append((None, (str(filename),)))
        else:
            talk[-1] = (chat_query, response)
    history[-1] = (query, full_response)
    print("С��: " + full_response)
    # if not last_yield_done:
    #     yield talk[-1]


# async def format_predict_output(generator):
#     async for items in generator:
#         # ��itemsת��ΪJSON�ַ�����������Ϊ�ֽ����У�Ȼ��yield
#         yield json.dumps(items).encode('utf-8') + b'\n'

async def format_predict_output(generator):
    async for items in generator:
        # Now items is just the last (question, answer) pair, so we format it directly
        yield json.dumps(items).encode('utf-8') + b'\n'


import json

# ������������ǰ��ӳ��
user_id_to_index = {}

# ���һ�����û�ID��������ӳ�亯��
def add_user_id(user_id):
    global user_id_to_index
    # ����û�ID�Ѿ����ڣ�ֱ�ӷ���������
    if user_id in user_id_to_index:
        return user_id_to_index[user_id]
    # ����Ϊ�����һ��������
    new_index = len(user_id_to_index)
    user_id_to_index[user_id] = new_index
    # ������º��ӳ�䵽�ļ�
    save_mapping_to_file()
    return new_index

# ���û�ID��������ӳ�䱣�浽JSON�ļ��ĺ���
def save_mapping_to_file(filename='user_id_to_index.json'):
    with open(filename, 'w') as file:
        json.dump(user_id_to_index, file)

@app.post("/chat")
async def chat(user_id: int = Form(...), query: str = Form(...),file: Optional[UploadFile] = File(None)):
    new_id=add_user_id(user_id)
    #����Ӧ����һ�����ղ��洢ͼƬ��ģ��
    image_paths=None
    print(file)
    if file:
        all_talk[new_id],all_history[new_id],image_paths=await add_file(history=all_talk[new_id],task_history=all_history[new_id],file=file)
        #print("OK")
    all_talk[new_id],all_history[new_id]=add_text(history=all_talk[new_id],task_history=all_history[new_id],text=query)

    # ���� predict���������߼�(��ʽ���)

    return StreamingResponse(format_predict_output(predict(talk=all_talk[new_id], history=all_history[new_id], file=image_paths)), media_type="text/event-stream")


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8007)
