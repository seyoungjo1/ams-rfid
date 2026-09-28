package com.ams.rfid.core

/**
 * 덤프에서 사람이 읽을 수 있는 필라멘트 정보를 추출한다.
 * 필드 위치는 공개된 Bambu 태그 포맷 문서(parse.py)와 동일하다.
 */
data class FilamentInfo(
    val uid: String,
    val filamentType: String,
    val detailedType: String,
    val colorHex: String,
    val secondColorHex: String?,
    val spoolWeightGram: Int,
    val diameterMm: Double,
    val minHotendC: Int,
    val maxHotendC: Int,
    val bedTempC: Int,
    val dryingTempC: Int,
    val dryingTimeH: Int,
    val productionDate: String,
) {
    companion object {
        fun parse(dump: TagDump): FilamentInfo {
            val b1 = dump.block(1)
            val b2 = dump.block(2)
            val b4 = dump.block(4)
            val b5 = dump.block(5)
            val b6 = dump.block(6)
            val b12 = dump.block(12)
            val b16 = dump.block(16)

            val hasExtraColor = b16[0] == 0x02.toByte() && b16[1] == 0x00.toByte()
            val colorCount = if (hasExtraColor) le16(b16, 2) else 1

            val second = if (colorCount == 2) {
                "#" + byteArrayOf(b16[7], b16[6], b16[5], b16[4]).toHex()
            } else null

            return FilamentInfo(
                uid = dump.uidHex,
                filamentType = ascii(b2),
                detailedType = ascii(b4),
                colorHex = "#" + b5.copyOfRange(0, 4).toHex(),
                secondColorHex = second,
                spoolWeightGram = le16(b5, 4),
                diameterMm = leFloat(b5, 8).toDouble(),
                minHotendC = le16(b6, 10),
                maxHotendC = le16(b6, 8),
                bedTempC = le16(b6, 6),
                dryingTempC = le16(b6, 0),
                dryingTimeH = le16(b6, 2),
                productionDate = ascii(b12),
            )
        }

        private fun ascii(b: ByteArray): String =
            b.toString(Charsets.US_ASCII).replace('\u0000', ' ').trim()

        private fun le16(b: ByteArray, offset: Int): Int =
            (b[offset].toInt() and 0xFF) or ((b[offset + 1].toInt() and 0xFF) shl 8)

        private fun leFloat(b: ByteArray, offset: Int): Float {
            val bits = (b[offset].toInt() and 0xFF) or
                ((b[offset + 1].toInt() and 0xFF) shl 8) or
                ((b[offset + 2].toInt() and 0xFF) shl 16) or
                ((b[offset + 3].toInt() and 0xFF) shl 24)
            return Float.fromBits(bits)
        }
    }
}
