import os
import uuid
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash
from google.cloud import firestore
from werkzeug.utils import secure_filename

# --- Konfigurasi Aplikasi ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.secret_key = os.getenv('SECRET_KEY', 'supersecretkey_for_a_bigger_app')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# --- Inisialisasi Firestore ---
db = None
try:
    if os.path.exists("firestore_key.json"):
        db = firestore.Client.from_service_account_json("firestore_key.json")
    else:
        db = firestore.Client()
    COLLECTION_NAME = "tanaman_hias"
except Exception as e:
    print(f"Error initializing Firestore: {e}")
    db = None

# --- Fungsi Bantuan ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_all_tags():
    if not db:
        return []
    all_tags = set()
    try:
        docs = db.collection(COLLECTION_NAME).stream()
        for doc in docs:
            doc_data = doc.to_dict()
            if 'tags' in doc_data and doc_data['tags']:
                all_tags.update(doc_data['tags'])
    except Exception as e:
        print(f"Error fetching tags: {e}")
    return sorted(list(all_tags))

def get_db_client():
    if db is None:
        flash("Error: Koneksi ke Firestore gagal. Periksa konfigurasi Anda.", "danger")
        return None
    return db

# --- Rute Utama (Routes) ---
@app.route('/')
def index():
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500
    
    search = request.args.get('search', '').lower()
    tag_filter = request.args.get('tag', '')

    try:
        query = db_client.collection(COLLECTION_NAME)
        if tag_filter:
            query = query.where('tags', 'array_contains', tag_filter)
        docs = query.stream()
        tanaman = [doc.to_dict() | {'id': doc.id} for doc in docs]

        if search:
            tanaman = [t for t in tanaman if
                       search in t.get('nama', '').lower() or
                       search in t.get('jenis', '').lower()]

        all_tags = get_all_tags()
        return render_template('index.html', tanaman=tanaman, search=search, all_tags=all_tags, active_tag=tag_filter)
    except Exception as e:
        flash(f"Terjadi kesalahan saat mengambil data: {e}", "danger")
        return render_template('error.html', message="Gagal mengambil data tanaman."), 500

@app.route('/dashboard')
def dashboard():
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500

    search = request.args.get('search', '').lower()
    filter_option = request.args.get('filter', '')
    all_tasks = []
    today = datetime.now().date()

    try:
        plants = db_client.collection(COLLECTION_NAME).stream()
        for plant in plants:
            plant_data = plant.to_dict()
            plant_id = plant.id
            schedules = db_client.collection(COLLECTION_NAME).document(plant_id).collection('jadwal').stream()

            for schedule in schedules:
                task = schedule.to_dict()
                task['id'] = schedule.id
                task['plant_id'] = plant_id
                task['plant_name'] = plant_data.get('nama', 'N/A')
                task['plant_gambar'] = plant_data.get('gambar', '')
                
                tanggal_berikutnya = task.get('tanggal_berikutnya')
                if not tanggal_berikutnya:
                    continue
                
                if isinstance(tanggal_berikutnya, firestore.Timestamp):
                    task['tanggal_berikutnya'] = tanggal_berikutnya.astimezone().replace(tzinfo=None)
                elif isinstance(tanggal_berikutnya, str):
                    try:
                        task['tanggal_berikutnya'] = datetime.fromisoformat(tanggal_berikutnya)
                    except ValueError:
                        continue
                
                if not isinstance(task.get('tanggal_berikutnya'), datetime):
                    continue

                delta_days = (task['tanggal_berikutnya'].date() - today).days
                
                if search and search not in task['plant_name'].lower() and search not in task['aktivitas'].lower():
                    continue
                
                if filter_option == 'today' and delta_days != 0:
                    continue
                elif filter_option == '3days' and delta_days > 3:
                    continue
                elif filter_option == 'overdue' and delta_days >= 0:
                    continue
                
                all_tasks.append(task)
    except Exception as e:
        flash(f"Terjadi kesalahan saat memuat data dashboard: {e}", "danger")

    all_tasks.sort(key=lambda x: x.get('tanggal_berikutnya', datetime.max))
    
    total_tasks = len(all_tasks)
    today_tasks = len([t for t in all_tasks if (t.get('tanggal_berikutnya', datetime.min).date() - today).days == 0])
    overdue_tasks = len([t for t in all_tasks if (t.get('tanggal_berikutnya', datetime.max).date() - today).days < 0])

    timeline_days = []
    for i in range(7):
        day_date = today + timedelta(days=i)
        count = sum(1 for t in all_tasks if t.get('tanggal_berikutnya', datetime.min).date() == day_date)
        timeline_days.append({"date": day_date, "tasks_count": count})

    return render_template('dashboard.html', tasks=all_tasks, now=datetime.now(), total_tasks=total_tasks,
                           today_tasks=today_tasks, overdue_tasks=overdue_tasks, search=search,
                           filter_option=filter_option, timeline_days=timeline_days)


@app.route('/view/<id>')
def view(id):
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500
    
    try:
        ref = db_client.collection(COLLECTION_NAME).document(id)
        tanaman = ref.get()
        if not tanaman.exists:
            flash("Tanaman tidak ditemukan.", "warning")
            return redirect(url_for('index'))

        jurnal_ref = ref.collection('jurnal').order_by('tanggal', direction=firestore.Query.DESCENDING).stream()
        jurnal_entries = [entry.to_dict() | {'id': entry.id} for entry in jurnal_ref]
        
        jadwal_ref = ref.collection('jadwal').order_by('tanggal_berikutnya').stream()
        jadwal_entries = []
        for entry in jadwal_ref:
            data = entry.to_dict()
            tanggal_berikutnya = data.get('tanggal_berikutnya')
            if isinstance(tanggal_berikutnya, firestore.Timestamp):
                data['tanggal_berikutnya'] = tanggal_berikutnya.astimezone()
            jadwal_entries.append(data | {'id': entry.id})

        return render_template('detail.html', tanaman=tanaman.to_dict() | {'id': id}, jurnal=jurnal_entries, jadwal=jadwal_entries)
    except Exception as e:
        flash(f"Terjadi kesalahan saat memuat detail tanaman: {e}", "danger")
        return redirect(url_for('index'))

@app.route('/add', methods=['GET', 'POST'])
def add():
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500
    
    if request.method == 'POST':
        try:
            gambar_url = ""
            file = request.files.get('gambar')
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                gambar_url = f"uploads/{filename}"

            tags = [tag.strip().lower() for tag in request.form.get('tags', '').split(',') if tag.strip()]
            
            doc_id = str(uuid.uuid4())
            db_client.collection(COLLECTION_NAME).document(doc_id).set({
                'nama': request.form['nama'],
                'jenis': request.form['jenis'],
                'lokasi_asal': request.form['lokasi_asal'],
                'cara_perawatan': request.form['cara_perawatan'],
                'gambar': gambar_url,
                'tags': tags
            })
            flash('Tanaman baru berhasil ditambahkan!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Gagal menambahkan tanaman: {e}", "danger")
    
    return render_template('add.html')

@app.route('/edit/<id>', methods=['GET', 'POST'])
def edit(id):
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500

    ref = db_client.collection(COLLECTION_NAME).document(id)
    tanaman = ref.get()
    if not tanaman.exists:
        flash("Tanaman tidak ditemukan.", "warning")
        return redirect(url_for('index'))

    data = tanaman.to_dict()
    if request.method == 'POST':
        try:
            file = request.files.get('gambar')
            gambar_url = data.get('gambar', '')
            if file and allowed_file(file.filename):
                if gambar_url and os.path.exists(os.path.join('static', gambar_url)):
                    os.remove(os.path.join('static', gambar_url))
                filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                gambar_url = f"uploads/{filename}"

            tags = [tag.strip().lower() for tag in request.form.get('tags', '').split(',') if tag.strip()]
            
            ref.update({
                'nama': request.form['nama'],
                'jenis': request.form['jenis'],
                'lokasi_asal': request.form['lokasi_asal'],
                'cara_perawatan': request.form['cara_perawatan'],
                'gambar': gambar_url,
                'tags': tags
            })
            flash('Data tanaman berhasil diperbarui!', 'info')
            return redirect(url_for('view', id=id))
        except Exception as e:
            flash(f"Gagal memperbarui tanaman: {e}", "danger")

    data['tags'] = ', '.join(data.get('tags', []))
    return render_template('edit.html', tanaman=data | {'id': id})

@app.route('/delete/<id>', methods=['POST'])
def delete(id):
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500

    ref = db_client.collection(COLLECTION_NAME).document(id)
    tanaman = ref.get()
    
    if not tanaman.exists:
        flash('Tanaman tidak ditemukan.', 'danger')
        return redirect(url_for('index'))

    try:
        data = tanaman.to_dict()
        gambar_url = data.get('gambar', '')
        if gambar_url and os.path.exists(os.path.join('static', gambar_url)):
            os.remove(os.path.join('static', gambar_url))
        
        def delete_collection(coll_ref, batch_size):
            docs = coll_ref.limit(batch_size).stream()
            deleted = 0
            for doc in docs:
                doc.reference.delete()
                deleted += 1
            if deleted >= batch_size:
                return delete_collection(coll_ref, batch_size)

        delete_collection(ref.collection('jurnal'), 100)
        delete_collection(ref.collection('jadwal'), 100)
        
        ref.delete()
        flash('Tanaman dan data terkait berhasil dihapus.', 'danger')
    except Exception as e:
        flash(f"Gagal menghapus tanaman: {e}", "danger")
        print(f"Error during plant deletion: {e}")
        
    return redirect(url_for('index'))

@app.route('/plant/<plant_id>/jurnal/add', methods=['POST'])
def add_jurnal(plant_id):
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500
    try:
        db_client.collection(COLLECTION_NAME).document(plant_id).collection('jurnal').add({
            'tanggal': firestore.SERVER_TIMESTAMP,
            'catatan': request.form['catatan']
        })
        flash('Catatan jurnal berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f"Gagal menambahkan catatan jurnal: {e}", "danger")
    return redirect(url_for('view', id=plant_id))

@app.route('/plant/<plant_id>/jurnal/<jurnal_id>/edit', methods=['GET', 'POST'])
def edit_jurnal(plant_id, jurnal_id):
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500
    ref = db_client.collection(COLLECTION_NAME).document(plant_id).collection('jurnal').document(jurnal_id)
    entry = ref.get()
    if not entry.exists:
        flash('Catatan jurnal tidak ditemukan.', 'danger')
        return redirect(url_for('view', id=plant_id))

    if request.method == 'POST':
        try:
            catatan_baru = request.form.get('catatan', '')
            if catatan_baru:
                ref.update({'catatan': catatan_baru})
                flash('Catatan jurnal berhasil diperbarui!', 'info')
            else:
                flash('Catatan tidak boleh kosong.', 'warning')
            return redirect(url_for('view', id=plant_id))
        except Exception as e:
            flash(f"Gagal memperbarui catatan jurnal: {e}", "danger")
    
    data = entry.to_dict()
    return render_template('edit_jurnal.html', plant_id=plant_id, jurnal_id=jurnal_id, catatan=data.get('catatan', ''))

@app.route('/plant/<plant_id>/jurnal/<jurnal_id>/delete', methods=['POST'])
def delete_jurnal(plant_id, jurnal_id):
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500
    try:
        db_client.collection(COLLECTION_NAME).document(plant_id).collection('jurnal').document(jurnal_id).delete()
        flash('Catatan jurnal telah dihapus.', 'danger')
    except Exception as e:
        flash(f"Gagal menghapus catatan jurnal: {e}", "danger")
    return redirect(url_for('view', id=plant_id))

@app.route('/plant/<plant_id>/jadwal/add', methods=['POST'])
def add_jadwal(plant_id):
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500
    try:
        frekuensi_str = request.form.get('frekuensi')
        aktivitas = request.form.get('aktivitas')
        
        if not frekuensi_str or not aktivitas:
            flash('Frekuensi dan aktivitas tidak boleh kosong.', 'warning')
            return redirect(url_for('view', id=plant_id))

        frekuensi = int(frekuensi_str)
        if frekuensi <= 0:
            flash('Frekuensi harus angka positif.', 'danger')
            return redirect(url_for('view', id=plant_id))
        
        tanggal_berikutnya = datetime.now() + timedelta(days=frekuensi)

        db_client.collection(COLLECTION_NAME).document(plant_id).collection('jadwal').add({
            'aktivitas': aktivitas,
            'frekuensi': frekuensi,
            'tanggal_berikutnya': tanggal_berikutnya
        })
        flash('Jadwal perawatan berhasil ditambahkan!', 'success')
    except (ValueError, TypeError) as e:
        flash(f'Input tidak valid: {e}. Frekuensi harus berupa angka.', 'danger')
    except Exception as e:
        flash(f'Gagal menambahkan jadwal: {e}', 'danger')
    return redirect(url_for('view', id=plant_id))

@app.route('/plant/<plant_id>/jadwal/<jadwal_id>/complete', methods=['POST'])
def complete_jadwal(plant_id, jadwal_id):
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500
    
    next_url = request.form.get('next_page', 'view')

    ref = db_client.collection(COLLECTION_NAME).document(plant_id).collection('jadwal').document(jadwal_id)
    jadwal = ref.get()
    
    if not jadwal.exists:
        flash('Jadwal tidak ditemukan.', 'danger')
        return redirect(url_for('view', id=plant_id))

    try:
        data = jadwal.to_dict()
        frekuensi = int(data.get('frekuensi', 7))
        new_date = datetime.now().replace(microsecond=0) + timedelta(days=frekuensi)
        ref.update({'tanggal_berikutnya': new_date})
        flash(f"Tugas '{data.get('aktivitas', 'N/A')}' selesai! Jadwal berikutnya diperbarui.", 'success')
    except Exception as e:
        flash(f"Gagal menyelesaikan jadwal: {e}", "danger")

    if next_url == 'dashboard':
        return redirect(url_for('dashboard'))
    return redirect(url_for('view', id=plant_id))

@app.route('/plant/<plant_id>/jadwal/<jadwal_id>/delete', methods=['POST'])
def delete_jadwal(plant_id, jadwal_id):
    db_client = get_db_client()
    if not db_client:
        return render_template('error.html', message="Koneksi ke database gagal."), 500
    try:
        db_client.collection(COLLECTION_NAME).document(plant_id).collection('jadwal').document(jadwal_id).delete()
        flash('Jadwal perawatan dihapus.', 'danger')
    except Exception as e:
        flash(f"Gagal menghapus jadwal: {e}", "danger")
    return redirect(url_for('view', id=plant_id))

@app.route('/error')
def error_page():
    message = request.args.get('message', 'Terjadi kesalahan yang tidak terduga.')
    return render_template('error.html', message=message), 500

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
    