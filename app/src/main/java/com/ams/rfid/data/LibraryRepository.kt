package com.ams.rfid.data

import android.content.Context
import com.ams.rfid.BuildConfig
import com.ams.rfid.core.LibraryUpdate
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** 게시된 DB의 요약(manifest.json). */
data class LibraryManifest(
    val format: Int,
    val commit: String,
    val generated: String,
    val colors: Int,
    val samples: Int,
    val keys: List<String>,
)

/**
 * 필라멘트 DB 저장소.
 *
 * - 앱에 내장된 DB(assets)와 내려받은 DB(filesDir) 중 더 최근에 만들어진 것을 쓴다.
 *   (앱을 새 버전으로 업데이트해 내장 DB가 더 최신이 되면 자동으로 내장 DB로 돌아간다.)
 * - GitHub 'library-db' 릴리스의 manifest.json 으로 새 DB가 있는지 확인하고,
 *   사용자가 동의하면 index.json 을 내려받아 교체한다.
 */
class LibraryRepository(private val context: Context) {

    private val dir = File(context.filesDir, "library")
    private val downloaded = File(dir, "index.json")
    private val baseUrl = "https://github.com/${BuildConfig.LIBRARY_REPO}/releases/download/library-db"

    fun load(): FilamentLibrary {
        val bundledText = context.assets.open(ASSET_PATH).bufferedReader().use { it.readText() }
        val downloadedText = if (downloaded.exists()) runCatching { downloaded.readText() }.getOrNull() else null

        if (downloadedText != null) {
            val bundledGen = LibraryUpdate.peekGenerated(bundledText.take(HEAD_CHARS)).orEmpty()
            val downloadedGen = LibraryUpdate.peekGenerated(downloadedText.take(HEAD_CHARS)).orEmpty()
            if (downloadedGen > bundledGen) {
                runCatching { return FilamentLibrary.parse(downloadedText, LibrarySource.DOWNLOADED) }
                // 손상된 파일이면 지우고 내장 DB를 쓴다.
                downloaded.delete()
            } else {
                // 내장 DB가 더 최신이면 오래된 내려받은 DB는 정리한다.
                downloaded.delete()
            }
        }
        return FilamentLibrary.parse(bundledText, LibrarySource.BUNDLED)
    }

    @Throws(IOException::class)
    fun fetchManifest(): LibraryManifest {
        val root = JSONObject(String(httpGet("$baseUrl/manifest.json"), Charsets.UTF_8))
        val keysArr = root.optJSONArray("keys")
        val keys = if (keysArr == null) emptyList() else List(keysArr.length()) { keysArr.getString(it) }
        return LibraryManifest(
            format = root.optInt("format", 0),
            commit = root.optString("commit", ""),
            generated = root.optString("generated", ""),
            colors = root.optInt("colors", keys.size),
            samples = root.optInt("samples", 0),
            keys = keys,
        )
    }

    /** index.json 을 내려받아 검증한 뒤 교체한다. 검증에 실패하면 기존 DB를 그대로 둔다. */
    @Throws(IOException::class)
    fun download(manifest: LibraryManifest): FilamentLibrary {
        val text = String(httpGet("$baseUrl/index.json"), Charsets.UTF_8)
        val library = try {
            FilamentLibrary.parse(text, LibrarySource.DOWNLOADED)
        } catch (e: Exception) {
            throw IOException("DB 형식 오류: ${e.message}")
        }
        if (library.entries.isEmpty()) throw IOException("DB가 비어 있습니다")
        if (library.commit != manifest.commit) throw IOException("DB가 갱신 중입니다. 잠시 후 다시 시도하세요")

        dir.mkdirs()
        val tmp = File(dir, "index.json.tmp")
        tmp.writeText(text)
        if (!tmp.renameTo(downloaded)) {
            tmp.delete()
            throw IOException("DB 저장 실패")
        }
        return library
    }

    private fun httpGet(url: String): ByteArray {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 30_000
            instanceFollowRedirects = true
            setRequestProperty("User-Agent", "ams-rfid/${BuildConfig.VERSION_NAME}")
        }
        try {
            val code = conn.responseCode
            if (code == HttpURLConnection.HTTP_NOT_FOUND) throw IOException("게시된 DB가 없습니다")
            if (code != HttpURLConnection.HTTP_OK) throw IOException("HTTP $code")
            return conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }

    private companion object {
        const val ASSET_PATH = "library/index.json"
        const val HEAD_CHARS = 512
    }
}
