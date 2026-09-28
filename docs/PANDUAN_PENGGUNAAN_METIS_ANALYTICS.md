# Panduan Singkat METIS Analytics

**Vibration Analysis Software — Windows 10/11 64-bit**

> METIS Analytics adalah alat bantu engineering. Selalu cocokkan hasil dengan
> kondisi lapangan, konfigurasi sensor, standar yang berlaku, dan pertimbangan
> engineer yang kompeten.

## 1. Ekstrak dan jalankan

1. Klik kanan `Metis Analytics.rar`.
2. Pilih **Extract to "METIS Analytics\\"** menggunakan WinRAR atau 7-Zip.
3. Buka folder hasil ekstraksi.
4. Pastikan `METIS Analytics.exe` dan folder `_internal` berada dalam folder
   yang sama.
5. Klik dua kali `METIS Analytics.exe`.

Jangan menjalankan aplikasi langsung dari dalam WinRAR/7-Zip dan jangan
memindahkan file `.exe` sendirian. Jika aplikasi dipindahkan ke komputer lain,
salin seluruh folder `METIS Analytics`.

METIS akan membuka halaman lokal di browser dan menampilkan ikon di system
tray. Menutup tab browser tidak menghentikan aplikasi:

- **Open METIS Analytics**: membuka kembali halaman aplikasi.
- **Exit METIS Analytics**: menutup aplikasi dengan benar.

## 2. Browser untuk laporan PDF

Browser yang menampilkan aplikasi dan browser untuk membuat grafik PDF adalah
dua hal berbeda. Browser default Windows tidak menentukan browser PDF.

### Chrome atau Edge

METIS otomatis mencari Google Chrome, lalu Microsoft Edge. Tidak diperlukan
pengaturan tambahan.

Di halaman **Print Report**, buka **PDF chart renderer diagnostics**, periksa
nama/path browser, lalu klik **Run renderer self-test**.

### Brave atau browser Chromium lain

Brave dapat digunakan, tetapi harus diatur melalui `BROWSER_PATH`.

Buka PowerShell dan coba path berikut:

```powershell
$Brave = "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe"
if (-not (Test-Path $Brave)) {
    $Brave = "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
}
Test-Path $Brave
```

Jika hasilnya `True`, simpan konfigurasi:

```powershell
[Environment]::SetEnvironmentVariable("BROWSER_PATH", $Brave, "User")
```

Keluar dari METIS melalui system tray, lalu jalankan kembali. Diagnostics akan
menampilkan **Chromium browser (BROWSER_PATH)**. Jalankan self-test sebelum
membuat report.

Firefox dapat membuka antarmuka METIS, tetapi tidak dapat digunakan untuk
membuat grafik PDF.

## 3. Tambahkan data

1. Buka panel **Add Files**.
2. Klik **Upload** atau **Add files**.
3. Pilih satu atau beberapa file `.sis` atau `.csv`.
4. Gunakan **Active file** untuk berpindah antarfile.

Periksa metadata seperti tanggal, waktu, serial number, sampling rate/interval,
channel, dan satuan sebelum melakukan analisis.

## 4. Menu analisis

### Waveform

- **Data Overview**: informasi rekaman, nilai puncak, frekuensi, PVS, dan
  compliance.
- **Signal Analysis**: waveform, FFT/frekuensi, acceleration, dan displacement.
- **Signature Hole Analysis**: simulasi pola delay dari signature hole.
- **Attenuation & Safe Zone**: regresi PPV, prediksi jarak aman, berat isian,
  atau PPV.

Hasil simulasi dan prediksi sangat bergantung pada kualitas serta
keterwakilan data input dan bukan jaminan kondisi aktual.

### Bargraph Monitoring

- **Data Overview**: durasi, interval, kualitas data, maksimum, mean, median,
  P95, dan P99.
- **Trends**: tren berdasarkan interval atau agregasi waktu.
- **Events & Thresholds**: event yang melewati ambang operasional pengguna.
- **PPV Compliance**: evaluasi interval velocity yang memiliki satuan dan
  frekuensi valid.

Ambang pada **Events & Thresholds** adalah alarm operasional, bukan batas
regulasi. Nilai `Interval peak` juga tidak boleh dianggap RMS atau VDV kecuali
metadata alat menyatakannya demikian.

## 5. Buat laporan PDF

### Laporan waveform

1. Aktifkan file waveform dan pilih **Print Report**.
2. Isi nama project, pembuat laporan, client, dan catatan bila diperlukan.
3. Pilih file yang akan dimasukkan.
4. Pilih section tambahan: Records Summary, Acceleration + Displacement,
   dan/atau FFT Analysis.
5. Pilih standard, assessment duration, dan structure category yang sesuai.
6. Pastikan renderer self-test berhasil.
7. Klik **Generate PDF Report**, lalu **Download PDF Report**.

### Laporan monitoring

1. Aktifkan file bargraph dan pilih **Print Report**.
2. Isi detail laporan.
3. Pilih section: Overview, Trend, Events, dan/atau PPV Compliance.
4. Atur aggregation, statistic, event threshold, dan compliance bila section
   tersebut digunakan.
5. Klik **Generate Monitoring PDF**, lalu **Download Monitoring PDF**.

## 6. Baca hasil report

Periksa lebih dahulu identitas project, sumber file, waktu rekaman, serial
alat, channel, satuan, dan pengaturan compliance.

- **Peak per channel**: nilai puncak pada setiap arah/sensor.
- **PVS**: resultan maksimum tiga komponen getaran; tetap periksa setiap
  channel secara terpisah.
- **Frequency/FFT**: membantu mengenali kandungan frekuensi. Noise, amplitudo
  rendah, dan clipping dapat membuat estimasi kurang andal.
- **Acceleration/Displacement**: signal turunan dari velocity; tinjau baseline,
  noise, dan bentuk waveform sebelum digunakan untuk keputusan engineering.
- **Trend**: menunjukkan pola terhadap waktu; lonjakan singkat tetap perlu
  diperiksa pada data interval/event.
- **Events**: hasil pengelompokan berdasarkan threshold operasional pengguna,
  bukan otomatis pelanggaran standard.

Arti status compliance:

- **PASS**: semua hasil yang dapat dievaluasi berada pada atau di bawah limit.
- **FAIL**: sedikitnya satu hasil yang dapat dievaluasi melampaui limit.
- **REVIEW**: evaluasi manual diperlukan, misalnya frekuensi hilang/nol atau
  standard memerlukan pemeriksaan tambahan.

`PASS` bukan sertifikasi otomatis dan `REVIEW` bukan `PASS`. Interpretasi harus
mempertimbangkan standard, assessment duration, structure category, lokasi
pengukuran, kualitas data, dan kondisi lapangan.

## 7. Masalah umum

### Halaman aplikasi tidak terbuka

- Tunggu beberapa detik.
- Pilih **Open METIS Analytics** dari system tray.
- Pastikan firewall/antivirus tidak memblokir aplikasi lokal.

### `No supported browser was found`

- Instal Chrome atau Edge; atau
- atur `BROWSER_PATH` ke Brave/browser Chromium yang kompatibel;
- keluar melalui tray, buka kembali METIS, lalu jalankan self-test.

### Browser tidak dapat start

- Pastikan browser dapat dibuka normal.
- Pastikan `BROWSER_PATH` menunjuk langsung ke file `.exe`, bukan shortcut.
- Periksa antivirus atau application-control policy.

### Render timeout atau renderer crash

METIS otomatis membersihkan renderer dan mencoba sekali lagi. Jika tetap gagal:

1. Jalankan renderer self-test dan catat pesan error.
2. Keluar dari METIS melalui tray.
3. Jalankan kembali dan ulangi report.
4. Simpan nama file serta pesan diagnostics untuk investigasi.

## 8. Checklist sebelum membagikan report

- [ ] File dan metadata sudah benar.
- [ ] Standard, duration, category, dan basis pengukuran sesuai.
- [ ] Renderer self-test berhasil.
- [ ] Semua halaman PDF sudah diperiksa dan tidak terpotong/kosong.
- [ ] Status `REVIEW` sudah ditinjau manual.
- [ ] Event threshold tidak disebut sebagai batas regulasi.
- [ ] Interpretasi sudah ditinjau engineer yang berwenang.

---

METIS Analytics adalah perangkat lunak independen dan tidak berafiliasi dengan
Vibracord atau produsennya.
