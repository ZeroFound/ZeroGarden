document.addEventListener('DOMContentLoaded', () => {
    console.log('🌿 Zero Garden siap digunakan!');

    // 🌟 Intersection Observer untuk animasi fade-in saat elemen muncul
    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('fade-in');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.plant-card').forEach(card => observer.observe(card));

    // 🔔 Auto-close alert (Bootstrap)
    const alert = document.querySelector('.alert');
    if (alert && typeof bootstrap !== 'undefined' && bootstrap.Alert) {
        setTimeout(() => {
            new bootstrap.Alert(alert).close();
        }, 5000);
    }

    // 🌙 Dark Mode Toggle
    const toggleBtn = document.getElementById('toggleTheme');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const isDark = document.body.classList.toggle('dark-mode');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
        });
    }
    if (localStorage.getItem('theme') === 'dark') {
        document.body.classList.add('dark-mode');
    }

    // ⏳ Tampilkan spinner saat submit form
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', () => {
            const spinner = document.getElementById('loadingSpinner');
            if (spinner) spinner.classList.remove('d-none');
        });
    });

    // 🗑️ Konfirmasi hapus dengan SweetAlert2 jika tersedia
    document.querySelectorAll('.btn-danger').forEach(btn => {
        btn.addEventListener('click', e => {
            const confirmDelete = btn.dataset.confirm !== 'false';
            if (confirmDelete && typeof Swal !== 'undefined') {
                e.preventDefault();
                Swal.fire({
                    title: 'Yakin ingin menghapus?',
                    text: 'Data ini tidak bisa dikembalikan.',
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonText: 'Ya, hapus!',
                    cancelButtonText: 'Batal',
                }).then(result => {
                    if (result.isConfirmed) {
                        const href = btn.getAttribute('href') || btn.dataset.href;
                        if (href) {
                            window.location.href = href;
                        } else {
                            // fallback untuk button dalam form
                            btn.closest('form')?.submit();
                        }
                    }
                });
            }
        });
    });

    // 🔔 Fungsi Toast Global
    window.showToast = function (message) {
        const toastEl = document.getElementById('liveToast');
        if (!toastEl) return;
        const body = toastEl.querySelector('.toast-body');
        if (body) body.textContent = message;
        const toast = new bootstrap.Toast(toastEl);
        toast.show();
    };

    // ✅ Contoh penggunaan: showToast('Data berhasil disimpan!');
});
