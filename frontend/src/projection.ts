export type Point = [number, number];

/** Project drawing millimeters into the original, uncropped image pixel plane. */
export function projectPoint(point: Point, matrix: number[][]): Point | null {
  if (matrix.length !== 3 || matrix.some(row => row.length !== 3 || row.some(value => !Number.isFinite(value)))) return null;
  const [x, y] = point;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  const denominator = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2];
  if (!Number.isFinite(denominator) || Math.abs(denominator) < 1e-9) return null;
  const result: Point = [
    (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / denominator,
    (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / denominator,
  ];
  return result.every(Number.isFinite) ? result : null;
}

/** Small arrows follow each segment's direction rather than bisecting corner angles. */
export function directionArrows(points: Point[]): { start: Point; end: Point }[] {
  return points.slice(0, -1).flatMap((point, index) => {
    const next = points[index + 1];
    const dx = next[0] - point[0];
    const dy = next[1] - point[1];
    if (!Number.isFinite(dx) || !Number.isFinite(dy) || Math.hypot(dx, dy) < 1e-6) return [];
    return [{
      start: [point[0] + dx * 0.42, point[1] + dy * 0.42] as Point,
      end: [point[0] + dx * 0.62, point[1] + dy * 0.62] as Point,
    }];
  });
}
