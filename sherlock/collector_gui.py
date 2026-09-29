import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from sherlock.collector_app import (app_home, InstanceLock, reserve_session,
                                    preflight, run_collection, EXPECTED_SECONDS)

PHASES = {'baseline':'Исходное состояние', 'active':'Активная фаза', 'recovery':'Восстановление'}
SCENARIOS_RU = {'normal':'Обычная работа', 'cpu_load':'Нагрузка CPU',
                'memory_growth':'Выделение памяти', 'mixed':'CPU + память'}


class App:
    def __init__(self, window, root):
        self.window, self.root = window, root
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.started = 0
        self.result = None
        self.number = 0
        self.completed = 0
        window.title('SherlockBench Collector')
        window.geometry('760x660')
        window.minsize(680, 620)
        window.configure(bg='#101820')
        style = ttk.Style(window)
        style.theme_use('clam')
        style.configure('TFrame', background='#101820')
        style.configure('TLabel', background='#101820', foreground='#e4ecf2', font=('Segoe UI',11))
        style.configure('Title.TLabel', font=('Segoe UI',23,'bold'))
        style.configure('Muted.TLabel', foreground='#a9bac6', font=('Segoe UI',10))
        style.configure('TButton', font=('Segoe UI',11), padding=10)
        style.configure('Start.TButton', background='#36b6a4', foreground='#061a18', font=('Segoe UI',12,'bold'))
        style.configure('Horizontal.TProgressbar', background='#36b6a4', troughcolor='#24333f')
        frame = ttk.Frame(window, padding=26)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame,text='SHERLOCKBENCH',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Сбор Windows CPU / RAM · 12 экспериментов · около 66 минут',style='Muted.TLabel').pack(anchor='w',pady=(4,20))
        settings = {}
        try:
            if (root/'settings.json').exists():
                settings = json.loads((root/'settings.json').read_text('utf-8'))
        except (OSError, ValueError):
            messagebox.showwarning('Настройки','Не удалось прочитать настройки. Проверь код ПК и номер сессии.')
        self.machine = tk.StringVar(value=settings.get('machine_id',''))
        self.session = tk.StringVar(value=str(settings.get('next_sessions',{}).get(self.machine.get(),1)))
        row = ttk.Frame(frame)
        row.pack(fill='x')
        ttk.Label(row,text='Код компьютера').grid(row=0,column=0,sticky='w')
        ttk.Label(row,text='Следующий номер сессии').grid(row=0,column=1,sticky='w',padx=(20,0))
        self.machine_entry = ttk.Entry(row,textvariable=self.machine,width=24,font=('Segoe UI',12))
        self.machine_entry.grid(row=1,column=0,sticky='w',pady=6)
        self.session_entry = ttk.Entry(row,textvariable=self.session,width=12,font=('Segoe UI',12))
        self.session_entry.grid(row=1,column=1,sticky='w',padx=(20,0))
        ttk.Label(frame,text='Код выдаёт организатор: pc-02, pc-03… Если уже был s01, укажи 2.\nНе используй имя, почту или серийный номер. Сессия резервируется при старте.',style='Muted.TLabel',wraplength=660).pack(anchor='w',pady=(4,16))
        ttk.Label(frame,text='3 круга × 4 сценария',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(frame,text='Без нагрузки → CPU → память → смешанная нагрузка.\nВ следующих кругах порядок меняется. Фазы: 60 / 180 / 60 секунд.\n2 CPU worker · duty 0.5 · память до 256 MiB · интервал 5 секунд.',style='Muted.TLabel',wraplength=660).pack(anchor='w',pady=(6,14))
        ttk.Label(frame,text='Сохрани работу и подключи питание. Не запускай игры и другие тесты.\nСобираются CPU, RAM, swap, параметры ОС и оборудования.\nФайлы, имена процессов и личные документы не читаются. Отправки в сеть нет.',style='Muted.TLabel',wraplength=660).pack(anchor='w',pady=(0,18))
        self.status = tk.StringVar(value='Готов к сбору')
        self.detail = tk.StringVar(value='Нажми «Начать сбор», когда компьютер готов.')
        self.clock = tk.StringVar(value='')
        ttk.Label(frame,textvariable=self.status,font=('Segoe UI',13,'bold')).pack(anchor='w')
        ttk.Label(frame,textvariable=self.detail,wraplength=660,style='Muted.TLabel').pack(anchor='w',pady=5)
        self.progress = ttk.Progressbar(frame,maximum=12)
        self.progress.pack(fill='x',pady=8)
        ttk.Label(frame,textvariable=self.clock,style='Muted.TLabel').pack(anchor='w')
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x',pady=16)
        self.start_btn=ttk.Button(buttons,text='Начать сбор',style='Start.TButton',command=self.start)
        self.start_btn.pack(side='left')
        self.stop_btn=ttk.Button(buttons,text='Остановить',command=self.stop,state='disabled')
        self.stop_btn.pack(side='left',padx=10)
        ttk.Button(buttons,text='Результаты',command=self.open_results).pack(side='right')
        self.location=tk.StringVar(value='Результаты сохраняются локально. После сбора будет готов ZIP.')
        ttk.Label(frame,textvariable=self.location,wraplength=660,style='Muted.TLabel').pack(anchor='w')
        window.protocol('WM_DELETE_WINDOW',self.close)
        window.after(200,self.poll)

    def start(self):
        if self.running:
            return
        try:
            preflight()
            machine=self.machine.get().strip()
            session=reserve_session(self.root,machine,int(self.session.get()))
        except Exception as error:
            messagebox.showerror('Не удалось начать',str(error))
            return
        self.session.set(str(int(session[1:])+1))
        self.cancel.clear()
        self.running=True
        self.result=None
        self.completed=0
        self.started=time.monotonic()
        self.progress['value']=0
        self.start_btn['state']='disabled'
        self.stop_btn['state']='normal'
        self.machine_entry['state']=self.session_entry['state']='disabled'
        self.location.set(f'Сбор {machine} / {session}. Архив будет создан автоматически.')
        threading.Thread(target=self.worker,args=(machine,session),daemon=False).start()

    def worker(self,machine,session):
        try:
            result=run_collection(self.root,machine,session,self.cancel,lambda **event:self.events.put(event))
            self.events.put(dict(kind='done',**result))
        except Exception as error:
            self.events.put(dict(kind='fatal',text=str(error)))

    def stop(self):
        if self.running:
            self.cancel.set()
            self.stop_btn['state']='disabled'
            self.status.set('Останавливаю и сохраняю данные…')

    def close(self):
        if self.running:
            if messagebox.askyesno('Сбор продолжается','Остановить сбор? Неполные данные сохранятся. После остановки окно можно закрыть.'):
                self.stop()
        else:
            self.window.destroy()

    def open_results(self):
        folder=self.root/'exports'
        folder.mkdir(exist_ok=True)
        if os.name=='nt':
            os.startfile(str(folder))
        else:
            subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(folder)])

    def poll(self):
        while True:
            try:
                event=self.events.get_nowait()
            except queue.Empty:
                break
            kind=event['kind']
            if kind=='run':
                self.number=event['number']
                self.status.set(f"Эксперимент {self.number} / {event['total']} · {SCENARIOS_RU[event['scenario']]}")
            elif kind=='phase':
                self.detail.set(f"{PHASES[event['phase']]} · измерений: {event['sample_count']}")
                self.progress['value']=min(11.99,self.completed+event['sample_count']/60)
            elif kind=='completed_run':
                self.completed=event['completed']
                self.progress['value']=self.completed
            elif kind=='cooldown':
                self.detail.set(f"Пауза между экспериментами: {event['seconds']} секунд")
            elif kind=='warning':
                self.location.set(event['text'])
            elif kind in ('done','fatal'):
                self.running=False
                self.start_btn['state']='normal'
                self.stop_btn['state']='disabled'
                self.machine_entry['state']=self.session_entry['state']='normal'
                if kind=='fatal':
                    self.status.set('Ошибка сохранения или запуска')
                    self.detail.set('Исходные записи, если созданы, остались в папке batches.')
                    messagebox.showerror('Ошибка',event['text']+'\n'+str(self.root))
                else:
                    self.result=event
                    title={'completed':'Сбор завершён','interrupted':'Сбор остановлен','failed':'Сбор завершился с ошибкой'}[event['status']]
                    self.status.set(title)
                    self.detail.set(f"Завершено {event['completed']} из {event['planned']} экспериментов. ZIP готов.")
                    self.location.set(event['archive'])
                    messagebox.showinfo(title,'Нажми «Результаты» и отправь организатору ZIP.\nНеполные сборы отмечены в имени файла.')
        if self.running:
            elapsed=int(time.monotonic()-self.started)
            remaining=max(0,EXPECTED_SECONDS-elapsed)
            self.clock.set(f'Прошло {elapsed//60:02}:{elapsed%60:02} · осталось примерно {remaining//60:02}:{remaining%60:02}')
        self.window.after(200,self.poll)


def main():
    root=app_home()
    root.mkdir(parents=True,exist_ok=True)
    window=tk.Tk()
    window.withdraw()
    try:
        lock=InstanceLock(root/'collector.lock')
    except RuntimeError as error:
        messagebox.showerror('SherlockBench',str(error))
        window.destroy()
        return
    try:
        App(window,root)
        window.deiconify()
        window.mainloop()
    finally:
        lock.close()
