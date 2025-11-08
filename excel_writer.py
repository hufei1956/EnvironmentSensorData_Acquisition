
from datetime import datetime
from pathlib import Path
import xlwings as xw

class ExcelWriter:
    """Wrap xlwings for main-thread writes only."""
    def __init__(self, visible: bool = True):
        # NOTE: Use this class from the Tk main thread only.
        self.app = xw.App(visible=visible, add_book=False)
        self.wb = xw.Book()  # create a new empty workbook
        self.sheet = self.wb.sheets.active
        self._row = 2
        self._index = 1
        self._write_header()

    def _write_header(self):
        headers = ["Index","Time","Temperature","Humidity","CO2","NH3","CH4","H2S"]
        self.sheet.range('A1').value = headers

    def write_record(self, rec):
        """Write one DataRecord. Call from main/UI thread."""
        r = self._row
        s = self.sheet
        s.range(f"A{r}").value = self._index
        s.range(f"B{r}").value = rec.timestamp_str
        s.range(f"C{r}").value = rec.temperature
        s.range(f"D{r}").value = rec.humidity
        s.range(f"E{r}").value = rec.co2
        s.range(f"F{r}").value = rec.nh3
        s.range(f"G{r}").value = rec.ch4
        s.range(f"H{r}").value = rec.h2s
        self._row += 1
        self._index += 1

    def save_and_close(self, out_dir: str = ".", prefix: str = "data_") -> str:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"{prefix}{ts}.xlsx"
        self.wb.save(str(path))
        self.wb.close()
        self.app.quit()
        return str(path)
