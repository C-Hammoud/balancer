package com.financetracker.finance.application;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.StringReader;
import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DateUtil;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

/**
 * Port of budgeting/importer.py: read CSV/XLSX rows, detect columns, parse dates and amounts.
 * Pure functions (no store access).
 */
public final class StatementImporter {

    public static final List<String> DATE_FORMATS = List.of("auto", "dmy", "mdy", "ymd");
    static final Set<String> MONTH_FIRST_COUNTRIES = Set.of("US", "PH", "FM", "PW", "MH");

    public static final Map<String, Set<String>> HEADER_ALIASES = new LinkedHashMap<>();

    static {
        HEADER_ALIASES.put("date", Set.of("date", "txn_date", "transaction date", "txn date", "posted", "posting date",
                "value date", "booking date"));
        HEADER_ALIASES.put("description", Set.of("description", "desc", "memo", "details", "payee", "narrative", "name",
                "transaction details", "particulars", "remarks"));
        HEADER_ALIASES.put("amount", Set.of("amount", "amt", "value", "sum", "transaction amount"));
        HEADER_ALIASES.put("debit", Set.of("debit", "withdrawal", "withdrawals", "debit amount", "money out", "paid out"));
        HEADER_ALIASES.put("credit", Set.of("credit", "deposit", "deposits", "credit amount", "money in", "paid in"));
    }

    /** A file the importer cannot read; the message is shown to the user. */
    public static class ImportError extends RuntimeException {
        public ImportError(String message) {
            super(message);
        }
    }

    /** One row's fields (date, description, amount). */
    public record Fields(String date, String description, String amount) {
    }

    private StatementImporter() {
    }

    public static String defaultDateFormat(String country) {
        return MONTH_FIRST_COUNTRIES.contains(country == null ? "" : country.toUpperCase(Locale.ROOT)) ? "mdy" : "dmy";
    }

    /** UTF-8 (BOM stripped), then Arabic Windows (cp1256), then Latin-1. */
    public static String decodeBytes(byte[] raw) {
        for (String enc : List.of("UTF-8", "windows-1256", "ISO-8859-1")) {
            try {
                String text = Charset.forName(enc).newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(raw)).toString();
                if ("UTF-8".equals(enc) && text.startsWith("﻿")) {
                    text = text.substring(1);
                }
                return text;
            } catch (CharacterCodingException e) {
                // try the next encoding
            }
        }
        throw new ImportError("Could not read the file's text encoding. Save it as UTF-8 CSV and try again.");
    }

    public static List<List<String>> readRows(String filename, byte[] raw) {
        String name = filename == null ? "" : filename.toLowerCase(Locale.ROOT);
        if (name.endsWith(".xlsx")) {
            return readXlsx(raw);
        }
        if (name.endsWith(".csv")) {
            String text = decodeBytes(raw);
            char delimiter = sniffDelimiter(text.length() > 4096 ? text.substring(0, 4096) : text);
            List<List<String>> rows = new ArrayList<>();
            try (CSVParser parser = CSVFormat.DEFAULT.builder().setDelimiter(delimiter).setIgnoreEmptyLines(false).get()
                    .parse(new StringReader(text))) {
                for (CSVRecord r : parser) {
                    List<String> cells = new ArrayList<>();
                    r.forEach(cells::add);
                    // csv.reader yields [] for a blank line (row numbers in errors count it).
                    rows.add(cells.size() == 1 && cells.get(0).isEmpty() ? new ArrayList<>() : cells);
                }
            } catch (IOException | RuntimeException e) {
                throw new ImportError("Could not read the CSV file.");
            }
            return rows;
        }
        throw new ImportError("Upload a .csv or .xlsx file.");
    }

    /**
     * csv.Sniffer(delimiters=",;\\t") in practice: the candidate that appears the same non-zero
     * number of times on the most lines (outside quotes) wins; comma when nothing fits.
     */
    static char sniffDelimiter(String sample) {
        String[] lines = sample.split("\r\n|\n|\r");
        char best = ',';
        int bestScore = -1;
        for (char d : new char[] {',', ';', '\t'}) {
            Map<Integer, Integer> freq = new LinkedHashMap<>();
            int considered = 0;
            for (String line : lines) {
                if (line.isBlank()) {
                    continue;
                }
                considered++;
                int count = 0;
                boolean quoted = false;
                for (char c : line.toCharArray()) {
                    if (c == '"') {
                        quoted = !quoted;
                    } else if (c == d && !quoted) {
                        count++;
                    }
                }
                if (count > 0) {
                    freq.merge(count, 1, Integer::sum);
                }
            }
            int mode = freq.values().stream().max(Integer::compare).orElse(0);
            if (considered > 0 && mode > bestScore && mode > 0) {
                best = d;
                bestScore = mode;
            }
        }
        return best;
    }

    private static List<List<String>> readXlsx(byte[] raw) {
        try (Workbook wb = new XSSFWorkbook(new ByteArrayInputStream(raw))) {
            Sheet ws = wb.getSheetAt(0);
            List<List<String>> rows = new ArrayList<>();
            int maxCols = 0;
            int lastRow = ws.getLastRowNum();
            for (int r = 0; r <= lastRow; r++) {
                Row row = ws.getRow(r);
                List<String> cells = new ArrayList<>();
                if (row != null) {
                    for (int c = 0; c < row.getLastCellNum(); c++) {
                        cells.add(cellStr(row.getCell(c)));
                    }
                }
                maxCols = Math.max(maxCols, cells.size());
                rows.add(cells);
            }
            for (List<String> cells : rows) {
                while (cells.size() < maxCols) {
                    cells.add("");
                }
            }
            return rows;
        } catch (IOException | RuntimeException e) {
            throw new ImportError("Could not open the Excel file.");
        }
    }

    /** importer._cell_str: dates as ISO, numbers like Python str(), text stripped. */
    static String cellStr(Cell cell) {
        if (cell == null) {
            return "";
        }
        CellType type = cell.getCellType() == CellType.FORMULA ? cell.getCachedFormulaResultType() : cell.getCellType();
        switch (type) {
            case NUMERIC:
                if (DateUtil.isCellDateFormatted(cell)) {
                    LocalDateTime dt = cell.getLocalDateTimeCellValue();
                    return dt == null ? "" : dt.toLocalDate().toString();
                }
                double d = cell.getNumericCellValue();
                if (d == Math.rint(d) && !Double.isInfinite(d) && Math.abs(d) < 1e15) {
                    return String.valueOf((long) d);
                }
                return BigDecimal.valueOf(d).stripTrailingZeros().toPlainString();
            case BOOLEAN:
                return cell.getBooleanCellValue() ? "True" : "False";
            case STRING:
                return cell.getStringCellValue().strip();
            default:
                return "";
        }
    }

    /** Map header names to column indexes; null when the row is not a header. */
    public static Map<String, Integer> columnMap(List<String> headerRow) {
        List<String> cells = headerRow.stream().map(c -> c == null ? "" : c.strip().toLowerCase(Locale.ROOT)).toList();
        Map<String, Integer> mapping = new LinkedHashMap<>();
        HEADER_ALIASES.forEach((field, names) -> {
            for (int i = 0; i < cells.size(); i++) {
                if (names.contains(cells.get(i))) {
                    mapping.put(field, i);
                    break;
                }
            }
        });
        boolean hasAmount = mapping.containsKey("amount") || mapping.containsKey("debit") || mapping.containsKey("credit");
        if (mapping.containsKey("date") && mapping.containsKey("description") && hasAmount) {
            return mapping;
        }
        if (!cells.isEmpty() && HEADER_ALIASES.get("date").contains(cells.get(0))) {
            Map<String, Integer> fallback = new LinkedHashMap<>();
            fallback.put("date", 0);
            fallback.put("description", 1);
            fallback.put("amount", 2);
            return fallback;
        }
        return null;
    }

    /**
     * Accepts 1,234.56 / 1.234,56 / (12.50) / 12.50- / currency symbols or codes. Throws
     * IllegalArgumentException when no number can be read.
     */
    public static BigDecimal parseAmount(String raw) {
        String s = raw == null ? "" : raw.strip();
        if (s.isEmpty()) {
            throw new IllegalArgumentException("empty amount");
        }
        boolean negative = false;
        if (s.startsWith("(") && s.endsWith(")")) {
            negative = true;
            s = s.substring(1, s.length() - 1);
        }
        if (s.endsWith("-")) {
            negative = true;
            s = s.substring(0, s.length() - 1);
        }
        int first = -1;
        int last = -1;
        for (int i = 0; i < s.length(); i++) {
            if (Character.isDigit(s.charAt(i))) {
                if (first < 0) {
                    first = i;
                }
                last = i;
            }
        }
        if (first < 0) {
            throw new IllegalArgumentException("bad amount " + raw);
        }
        if (s.substring(0, first).contains("-")) {
            negative = !negative;
        }
        StringBuilder kept = new StringBuilder();
        for (char ch : s.substring(first, last + 1).toCharArray()) {
            if (Character.isDigit(ch) || ch == ',' || ch == '.') {
                kept.append(Character.isDigit(ch) ? (char) ('0' + Character.digit(ch, 10)) : ch);
            }
        }
        String n = kept.toString();
        if (n.contains(",") && n.contains(".")) {
            if (n.lastIndexOf(',') > n.lastIndexOf('.')) {
                n = n.replace(".", "").replace(",", ".");
            } else {
                n = n.replace(",", "");
            }
        } else if (n.contains(",")) {
            int idx = n.lastIndexOf(',');
            String head = n.substring(0, idx);
            String tail = n.substring(idx + 1);
            n = tail.length() >= 1 && tail.length() <= 2 ? head.replace(",", "") + "." + tail : n.replace(",", "");
        }
        BigDecimal value;
        try {
            value = new BigDecimal(n);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("bad amount " + raw);
        }
        return negative ? value.negate() : value;
    }

    /** Python str.isdigit for a non-empty string. */
    private static boolean isDigits(String s) {
        return !s.isEmpty() && s.chars().allMatch(Character::isDigit);
    }

    private static int toInt(String s) {
        int v = 0;
        for (char c : s.toCharArray()) {
            v = v * 10 + Character.digit(c, 10);
        }
        return v;
    }

    private static String[] splitDate(String s) {
        for (String sep : List.of("/", "-", ".")) {
            if (s.contains(sep)) {
                return s.split(java.util.regex.Pattern.quote(sep), -1);
            }
        }
        return null;
    }

    /**
     * ISO (YYYY-MM-DD) always works. Otherwise / - . separated: dmy, mdy, ymd, or auto (a part
     * above 12 decides, else dmy). Two-digit years are 20YY.
     */
    public static LocalDate parseDate(String raw, String dateFormat) {
        String s = raw == null ? "" : raw.strip();
        if (s.isEmpty()) {
            throw new IllegalArgumentException("empty date");
        }
        String head = s.length() >= 10 ? s.substring(0, 10) : s;
        try {
            if (head.length() == 10 && head.charAt(4) == '-' && head.charAt(7) == '-') {
                return LocalDate.parse(head);
            }
            s = s.split(" ")[0].split("T")[0];
            String[] parts = splitDate(s);
            if (parts == null || parts.length != 3) {
                throw new IllegalArgumentException("unrecognised date " + raw);
            }
            for (String p : parts) {
                if (!isDigits(p.strip())) {
                    throw new IllegalArgumentException("unrecognised date " + raw);
                }
            }
            int a = toInt(parts[0].strip());
            int b = toInt(parts[1].strip());
            int c = toInt(parts[2].strip());
            if ("ymd".equals(dateFormat) || parts[0].strip().length() == 4) {
                return LocalDate.of(a, b, c);
            }
            int year = c < 100 ? c + 2000 : c;
            if ("mdy".equals(dateFormat)) {
                return LocalDate.of(year, a, b);
            }
            if ("auto".equals(dateFormat)) {
                if (a > 12 && b <= 12) {
                    return LocalDate.of(year, b, a);
                }
                if (b > 12 && a <= 12) {
                    return LocalDate.of(year, a, b);
                }
            }
            return LocalDate.of(year, b, a);
        } catch (DateTimeException e) {
            throw new IllegalArgumentException("bad date " + raw);
        }
    }

    /** Pick dmy/mdy from the file when any date has a part above 12. */
    public static String guessDateFormat(List<String> dateStrings, String fallback) {
        for (String raw : dateStrings) {
            String s = (raw == null ? "" : raw.strip()).split(" ")[0];
            String[] parts = splitDate(s);
            if (parts == null) {
                continue;
            }
            if (parts.length != 3 || !isDigits(parts[0]) || !isDigits(parts[1]) || !isDigits(parts[2]) || parts[0].length() == 4) {
                continue;
            }
            int a = toInt(parts[0]);
            int b = toInt(parts[1]);
            if (a > 12 && b <= 12) {
                return "dmy";
            }
            if (b > 12 && a <= 12) {
                return "mdy";
            }
        }
        return fallback;
    }

    /** (date, description, amount) for one row; throws IndexOutOfBoundsException when too short. */
    public static Fields extractFields(List<String> row, Map<String, Integer> colMap) {
        if (colMap == null) {
            return new Fields(row.get(0).strip(), row.get(1).strip(), row.get(2).strip());
        }
        String amount = cell(row, colMap.get("amount"));
        if (amount.isEmpty() && (colMap.containsKey("debit") || colMap.containsKey("credit"))) {
            String debit = cell(row, colMap.get("debit"));
            String credit = cell(row, colMap.get("credit"));
            if (!credit.isEmpty() && parseAmount(credit).signum() != 0) {
                amount = parseAmount(credit).abs().toString();
            } else if (!debit.isEmpty()) {
                amount = parseAmount(debit).abs().negate().toString();
            }
        }
        return new Fields(cell(row, colMap.get("date")), cell(row, colMap.get("description")), amount);
    }

    private static String cell(List<String> row, Integer idx) {
        if (idx == null || idx >= row.size()) {
            return "";
        }
        String v = row.get(idx);
        return v == null ? "" : v.strip();
    }

    /**
     * Stable id for an imported row; `occurrence` counts identical rows within one file so two
     * genuine same-day purchases both import, while re-uploading adds nothing.
     */
    public static String dedupeKey(LocalDate date, BigDecimal amount, String description, int occurrence) {
        String desc = description.length() > 100 ? description.substring(0, 100) : description;
        String base = date + "|" + amount + "|" + desc;
        return occurrence <= 1 ? base : base + "#" + occurrence;
    }
}
