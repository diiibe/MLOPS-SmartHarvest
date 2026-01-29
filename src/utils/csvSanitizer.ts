/**
 * CSV Sanitizer Utility
 * Prevents CSV Injection (Formula Injection) by escaping dangerous characters.
 * 
 * Vulnerability:
 * If a cell value starts with =, +, -, or @, Excel and other spreadsheet software
 * may interpret it as a formula. If the value contains malicious code, it could be executed.
 * 
 * Mitigation:
 * Prepend a single quote (') to force the value to be treated as a string.
 */

export const sanitizeCell = (value: any): string => {
  if (value === null || value === undefined) {
    return '';
  }

  const stringValue = String(value);

  // Check for dangerous starting characters
  if (/^[=+\-@]/.test(stringValue)) {
    return `'${stringValue}`;
  }

  return stringValue;
};

/**
 * Sanitizes an array of objects for CSV export.
 * @param data Array of objects (rows)
 * @returns Array of objects with sanitized values
 */
export const sanitizeData = <T extends Record<string, any>>(data: T[]): T[] => {
  return data.map(row => {
    const sanitizedRow: Record<string, any> = {};
    Object.keys(row).forEach(key => {
      sanitizedRow[key] = sanitizeCell(row[key]);
    });
    return sanitizedRow as T;
  });
};
