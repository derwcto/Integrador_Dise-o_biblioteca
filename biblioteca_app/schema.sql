-- ============================================================================
-- schema.sql  —  Base de datos: biblioteca
-- Sistema de préstamos y devoluciones de una biblioteca
-- Compatible con MySQL 8.x
--
-- Uso:  python apply_schema.py        (recomendado, maneja los DELIMITER)
--   o:  mysql -u root -p < schema.sql
--
-- El script es idempotente: CREATE TABLE IF NOT EXISTS / DROP ... IF EXISTS.
-- Si tus tablas YA existen, revisa la sección "Contrato de datos" del README
-- para ajustar las columnas mínimas que necesita la aplicación.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS biblioteca
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE biblioteca;

-- ---------------------------------------------------------------------------
-- Tablas
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Libros (
  id_libro        INT NOT NULL AUTO_INCREMENT,
  titulo          VARCHAR(200) NOT NULL,
  isbn            VARCHAR(20)  NOT NULL,
  stock_disponible INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (id_libro),
  UNIQUE KEY uk_libros_isbn (isbn),
  CONSTRAINT chk_libros_stock CHECK (stock_disponible >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Lectores (
  id_lector  INT NOT NULL AUTO_INCREMENT,
  dni        VARCHAR(15)  NOT NULL,
  nombres    VARCHAR(150) NOT NULL,
  estado     VARCHAR(20)  NOT NULL DEFAULT 'ACTIVO',  -- ACTIVO / INACTIVO / MOROSO
  PRIMARY KEY (id_lector),
  UNIQUE KEY uk_lectores_dni (dni)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Prestamos (
  id_prestamo             INT NOT NULL AUTO_INCREMENT,
  id_lector               INT NOT NULL,
  fecha_prestamo          DATE NOT NULL DEFAULT (CURRENT_DATE),
  fecha_devolucion_pactada DATE NOT NULL,
  estado                  VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',  -- ACTIVO / DEVUELTO
  PRIMARY KEY (id_prestamo),
  KEY ix_prestamos_lector (id_lector, estado),
  CONSTRAINT fk_prestamos_lector
    FOREIGN KEY (id_lector) REFERENCES Lectores (id_lector)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Detalle_Prestamos (
  id_detalle              INT NOT NULL AUTO_INCREMENT,
  id_prestamo             INT NOT NULL,
  id_libro                INT NOT NULL,
  cantidad                INT NOT NULL DEFAULT 1,
  fecha_devolucion_pactada DATE NOT NULL,
  fecha_devolucion_real   DATE NULL,
  multa                   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  estado                  VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',  -- ACTIVO / DEVUELTO
  PRIMARY KEY (id_detalle),
  KEY ix_detalle_libro   (id_libro, estado),
  KEY ix_detalle_prestamo (id_prestamo),
  CONSTRAINT fk_detalle_prestamo
    FOREIGN KEY (id_prestamo) REFERENCES Prestamos (id_prestamo) ON DELETE CASCADE,
  CONSTRAINT fk_detalle_libro
    FOREIGN KEY (id_libro) REFERENCES Libros (id_libro)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Procedimiento: sp_RegistrarPrestamo
--   Registra un préstamo (cabecera en Prestamos + línea en Detalle_Prestamos),
--   valida lector activo y stock, y descuenta 1 unidad del stock del libro.
--   Devuelve un result set con id_prestamo, fecha pactada y mensaje.
--   Ante cualquier error hace ROLLBACK y lanza el error con SQLSTATE '45000'.
-- ---------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_RegistrarPrestamo;
DELIMITER $$
CREATE PROCEDURE sp_RegistrarPrestamo(
  IN p_id_lector     INT,
  IN p_id_libro      INT,
  IN p_dias_prestamo INT
)
BEGIN
  DECLARE v_estado_lector   VARCHAR(20);
  DECLARE v_nombres         VARCHAR(150);
  DECLARE v_stock           INT;
  DECLARE v_pactada         DATE;
  DECLARE v_id_prestamo     INT;

  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  IF p_dias_prestamo IS NULL OR p_dias_prestamo <= 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Los días de préstamo deben ser mayores que cero.';
  END IF;

  SET v_pactada = DATE_ADD(CURDATE(), INTERVAL p_dias_prestamo DAY);

  START TRANSACTION;

  -- Validar lector (bloqueo pesimista de la fila)
  SELECT estado, nombres INTO v_estado_lector, v_nombres
    FROM Lectores
   WHERE id_lector = p_id_lector
   FOR UPDATE;

  IF v_estado_lector IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El lector no existe.';
  ELSEIF v_estado_lector <> 'ACTIVO' THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'El lector no está ACTIVO.';
  END IF;

  -- Validar libro y stock (bloqueo pesimista de la fila)
  SELECT stock_disponible INTO v_stock
    FROM Libros
   WHERE id_libro = p_id_libro
   FOR UPDATE;

  IF v_stock IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El libro no existe.';
  ELSEIF v_stock <= 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'No hay stock disponible del libro.';
  END IF;

  -- Cabecera del préstamo
  INSERT INTO Prestamos (id_lector, fecha_prestamo, fecha_devolucion_pactada, estado)
  VALUES (p_id_lector, CURDATE(), v_pactada, 'ACTIVO');
  SET v_id_prestamo = LAST_INSERT_ID();

  -- Detalle del préstamo
  INSERT INTO Detalle_Prestamos
    (id_prestamo, id_libro, cantidad, fecha_devolucion_pactada, estado)
  VALUES
    (v_id_prestamo, p_id_libro, 1, v_pactada, 'ACTIVO');

  -- Descontar stock
  UPDATE Libros
     SET stock_disponible = stock_disponible - 1
   WHERE id_libro = p_id_libro;

  COMMIT;

  SELECT v_id_prestamo        AS id_prestamo,
         v_pactada            AS fecha_devolucion_pactada,
         CONCAT('Préstamo #', v_id_prestamo,
                ' registrado correctamente para ', v_nombres,
                '. Devolución pactada: ', DATE_FORMAT(v_pactada, '%d/%m/%Y'), '.') AS mensaje;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------------
-- Función: fn_CalcularMultaPorRetraso
--   Devuelve la multa en DECIMAL(10,2).
--   Tarifa: 1.00 unidad monetaria por cada día de retraso (0 si se devuelve a tiempo).
--   Ajusta la tarifa (1.00) en la variable v_multa si tu regla de negocio es distinta.
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS fn_CalcularMultaPorRetraso;
DELIMITER $$
CREATE FUNCTION fn_CalcularMultaPorRetraso(
  p_fecha_pactada DATE,
  p_fecha_real    DATE
)
RETURNS DECIMAL(10,2)
DETERMINISTIC
NO SQL
BEGIN
  DECLARE v_dias_retraso INT;

  SET v_dias_retraso = DATEDIFF(p_fecha_real, p_fecha_pactada);

  IF v_dias_retraso <= 0 THEN
    RETURN 0.00;
  END IF;

  RETURN v_dias_retraso * 1.00;   -- S/ 1.00 (o la moneda que manejes) por día de retraso
END$$
DELIMITER ;

-- ---------------------------------------------------------------------------
-- Datos de ejemplo (opcional). Puedes borrar esta sección si tu biblioteca
-- ya tiene datos.
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO Libros (id_libro, titulo, isbn, stock_disponible) VALUES
  (1, 'Cien años de soledad',                 '978-0307474728', 5),
  (2, 'Don Quijote de la Mancha',             '978-8420412146', 3),
  (3, 'El principito',                        '978-0156013987', 8),
  (4, 'Rayuela',                              '978-8437604572', 2),
  (5, 'La ciudad y los perros',               '978-8420469916', 4);

INSERT IGNORE INTO Lectores (id_lector, dni, nombres, estado) VALUES
  (1, '74859612', 'María Fernández Rojas',  'ACTIVO'),
  (2, '70541823', 'Carlos Mendoza Quispe',  'ACTIVO'),
  (3, '71632547', 'Lucía Torres Vega',      'ACTIVO'),
  (4, '70149876', 'Jorge Ramírez Castillo', 'INACTIVO');
