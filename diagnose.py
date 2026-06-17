f = open('diag.txt', 'w')

f.write('1 asyncio\n'); f.flush()
import asyncio

f.write('2 multiprocessing\n'); f.flush()
import multiprocessing

f.write('3 fastapi\n'); f.flush()
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

f.write('4 sqlalchemy\n'); f.flush()
from sqlalchemy import text

f.write('5 auth\n'); f.flush()
from app.api.routes.auth import router as auth_router

f.write('6 document\n'); f.flush()
from app.api.routes.document import router as document_router

f.write('7 pipeline_router\n'); f.flush()
from app.api.routes.document_pipeline_router import router as dp_router

f.write('8 draft\n'); f.flush()
from app.api.routes.draft_router import router as draft_router

f.write('9 notification_router\n'); f.flush()
from app.api.routes.notification_router import router as notif_router

f.write('10 db\n'); f.flush()
from app.db.database import engine, get_db

f.write('11 llm config\n'); f.flush()
from app.llm.config import CURRENT_MODEL, LLM_CONFIG

f.write('12 pipeline\n'); f.flush()
from app.llm.pipeline import invalidate_cache, run_query

f.write('13 notification_service\n'); f.flush()
from app.services import notification_service

f.write('14 vectorstore import\n'); f.flush()
from app.llm.vectorstore import get_vectorstore

f.write('15 vectorstore call\n'); f.flush()
get_vectorstore()

f.write('ALL DONE\n'); f.flush()
f.close()
print('ALL DONE')
