f = open('diag.txt', 'w')

f.write('1 asyncio\n'); f.flush()

f.write('2 multiprocessing\n'); f.flush()

f.write('3 fastapi\n'); f.flush()

f.write('4 sqlalchemy\n'); f.flush()

f.write('5 auth\n'); f.flush()

f.write('6 document\n'); f.flush()

f.write('7 pipeline_router\n'); f.flush()

f.write('8 draft\n'); f.flush()

f.write('9 notification_router\n'); f.flush()

f.write('10 db\n'); f.flush()

f.write('11 llm config\n'); f.flush()

f.write('12 pipeline\n'); f.flush()

f.write('13 notification_service\n'); f.flush()

f.write('14 vectorstore import\n'); f.flush()
from app.llm.vectorstore import get_vectorstore

f.write('15 vectorstore call\n'); f.flush()
get_vectorstore()

f.write('ALL DONE\n'); f.flush()
f.close()
print('ALL DONE')
