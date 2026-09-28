package com.ams.rfid.ui

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import com.ams.rfid.R
import com.ams.rfid.core.BambuKeys
import com.ams.rfid.core.CloneResult
import com.ams.rfid.core.CuidCheck
import com.ams.rfid.core.DumpValidator
import com.ams.rfid.core.FilamentInfo
import com.ams.rfid.core.LibraryUpdate
import com.ams.rfid.core.MifareCard
import com.ams.rfid.core.TagCloner
import com.ams.rfid.core.TagDump
import com.ams.rfid.data.FilamentEntry
import com.ams.rfid.data.FilamentLibrary
import com.ams.rfid.data.LibraryManifest
import com.ams.rfid.data.LibraryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.concurrent.thread

enum class Tab { LIBRARY, READ, HELP }

sealed interface LibraryState {
    data object Loading : LibraryState
    data class Ready(val library: FilamentLibrary) : LibraryState
    data class Error(val message: String) : LibraryState
}

/** 태그를 대면 실행할 대기 중인 작업. */
sealed interface Armed {
    data object None : Armed
    data class Write(val entry: FilamentEntry, val dump: TagDump) : Armed
    data object Read : Armed
    data object CuidCheck : Armed
}

/** 작업 진행/결과 상태. */
sealed interface OpStatus {
    data object Idle : OpStatus
    data class Progress(val message: String) : OpStatus
    data class Success(val message: String) : OpStatus
    data class Failure(val message: String) : OpStatus
    data class ReadDone(val info: FilamentInfo) : OpStatus
}

/** 필라멘트 DB 업데이트 상태. */
sealed interface UpdateState {
    data object Idle : UpdateState
    data object Checking : UpdateState
    /** 새 DB가 있어 사용자에게 업데이트할지 묻는 중. */
    data class Available(val manifest: LibraryManifest, val diff: LibraryUpdate.Diff) : UpdateState
    data object Downloading : UpdateState
    data class Message(val text: String) : UpdateState
}

data class UiState(
    val tab: Tab = Tab.LIBRARY,
    val library: LibraryState = LibraryState.Loading,
    val query: String = "",
    val results: List<FilamentEntry> = emptyList(),
    val selected: FilamentEntry? = null,
    val armed: Armed = Armed.None,
    val status: OpStatus = OpStatus.Idle,
    val update: UpdateState = UpdateState.Idle,
) {
    /** 태그를 대기하거나 결과를 보여주는 모달을 띄워야 하는지. */
    val showSheet: Boolean get() = armed != Armed.None || status != OpStatus.Idle
}

class MainViewModel(app: Application) : AndroidViewModel(app) {

    private val cloner = TagCloner()
    private val repository = LibraryRepository(app)
    private val prefs = app.getSharedPreferences("library", Context.MODE_PRIVATE)
    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    /** NFC 스레드와 DB 스레드가 동시에 상태를 바꾸므로 항상 원자적으로 갱신한다. */
    private inline fun set(crossinline transform: (UiState) -> UiState) = _ui.update { transform(it) }

    private val currentLibrary: FilamentLibrary?
        get() = (_ui.value.library as? LibraryState.Ready)?.library

    fun loadLibrary() {
        if (_ui.value.library is LibraryState.Ready) return
        thread(name = "library-load") {
            val state = try {
                LibraryState.Ready(repository.load())
            } catch (e: Exception) {
                LibraryState.Error(e.message ?: "라이브러리를 불러오지 못했습니다")
            }
            set { it.copy(library = state, results = (state as? LibraryState.Ready)?.library?.search(it.query) ?: emptyList()) }
            if (state is LibraryState.Ready) checkForUpdate(manual = false)
        }
    }

    // ---- 필라멘트 DB 업데이트 ----

    /**
     * 게시된 DB가 현재 DB보다 새로우면 사용자에게 업데이트할지 묻는다.
     * 자동 확인(앱 시작)은 조용히 실패하고, "나중에"로 넘긴 버전은 다시 묻지 않는다.
     * 수동 확인은 결과(최신/실패)를 항상 알려준다.
     */
    fun checkForUpdate(manual: Boolean) {
        val current = currentLibrary ?: return
        val busy = _ui.value.update
        if (busy is UpdateState.Checking || busy is UpdateState.Downloading || busy is UpdateState.Available) return
        if (manual) set { it.copy(update = UpdateState.Checking) }
        thread(name = "library-check") {
            val next: UpdateState = try {
                val manifest = repository.fetchManifest()
                val newer = LibraryUpdate.isNewer(
                    currentCommit = current.commit,
                    currentGenerated = current.generated,
                    remoteCommit = manifest.commit,
                    remoteGenerated = manifest.generated,
                    remoteFormat = manifest.format,
                )
                when {
                    !newer -> if (manual) UpdateState.Message(str(R.string.db_up_to_date)) else UpdateState.Idle
                    !manual && prefs.getString(KEY_SKIPPED, null) == manifest.commit -> UpdateState.Idle
                    else -> UpdateState.Available(manifest, LibraryUpdate.diff(current.keys, manifest.keys))
                }
            } catch (e: Exception) {
                if (manual) UpdateState.Message(str(R.string.db_check_failed, e.message ?: "")) else UpdateState.Idle
            }
            set { it.copy(update = next) }
        }
    }

    fun applyUpdate() {
        val available = _ui.value.update as? UpdateState.Available ?: return
        set { it.copy(update = UpdateState.Downloading) }
        thread(name = "library-download") {
            try {
                val lib = repository.download(available.manifest)
                prefs.edit().remove(KEY_SKIPPED).apply()
                set {
                    it.copy(
                        library = LibraryState.Ready(lib),
                        results = lib.search(it.query),
                        selected = null,
                        update = UpdateState.Message(str(R.string.db_update_done, lib.entries.size)),
                    )
                }
            } catch (e: Exception) {
                set { it.copy(update = UpdateState.Message(str(R.string.db_update_failed, e.message ?: ""))) }
            }
        }
    }

    /** "나중에": 이 버전은 앱 시작 시 다시 묻지 않는다(수동 확인으로는 받을 수 있음). */
    fun postponeUpdate() {
        val available = _ui.value.update as? UpdateState.Available ?: return
        prefs.edit().putString(KEY_SKIPPED, available.manifest.commit).apply()
        set { it.copy(update = UpdateState.Idle) }
    }

    fun dismissUpdateMessage() {
        set { if (it.update is UpdateState.Message) it.copy(update = UpdateState.Idle) else it }
    }

    // ---- 화면 상태 ----

    fun setTab(tab: Tab) = set { it.copy(tab = tab) }

    fun setQuery(query: String) = set {
        val lib = (it.library as? LibraryState.Ready)?.library
        it.copy(query = query, results = lib?.search(query) ?: emptyList())
    }

    fun select(entry: FilamentEntry?) = set { it.copy(selected = entry) }

    // ---- NFC 작업 ----

    fun armWrite(entry: FilamentEntry) {
        val sample = entry.samples.firstOrNull() ?: return
        val dump = try {
            sample.toDump()
        } catch (e: Exception) {
            set { it.copy(status = OpStatus.Failure(e.message ?: "덤프 오류")) }
            return
        }
        set { it.copy(armed = Armed.Write(entry, dump), status = OpStatus.Idle) }
    }

    fun armRead() = set { it.copy(armed = Armed.Read, status = OpStatus.Idle) }

    fun armCuidCheck() = set { it.copy(armed = Armed.CuidCheck, status = OpStatus.Idle) }

    fun dismissSheet() = set { it.copy(armed = Armed.None, status = OpStatus.Idle) }

    fun reportNotMifare() = set {
        if (it.armed == Armed.None) it
        else it.copy(armed = Armed.None, status = OpStatus.Failure(str(R.string.nfc_not_mifare)))
    }

    /** NFC 콜백 스레드에서 호출된다. 대기 중인 작업을 카드에 대해 실행한다. */
    fun executeOnCard(card: MifareCard) {
        val armed = _ui.value.armed
        if (armed == Armed.None) return
        try {
            card.connect()
            when (armed) {
                is Armed.Write -> runWrite(card, armed.dump)
                Armed.Read -> runRead(card)
                Armed.CuidCheck -> runCuidCheck(card)
                Armed.None -> {}
            }
        } catch (e: Exception) {
            failure(e.message ?: "오류")
        } finally {
            runCatching { card.close() }
            set { it.copy(armed = Armed.None) }
        }
    }

    private fun runWrite(card: MifareCard, dump: TagDump) {
        progress(str(R.string.nfc_working, 0, 16))
        val result = cloner.clone(card, dump) { done, total ->
            progress(str(R.string.nfc_working, done, total))
        }
        when (result) {
            is CloneResult.Success -> {
                progress(str(R.string.nfc_verifying))
                when (val v = cloner.verify(card, dump)) {
                    is CloneResult.Success -> success(str(R.string.nfc_write_success))
                    is CloneResult.Failure -> failure(str(R.string.nfc_verify_failed, v.message))
                }
            }
            is CloneResult.Failure -> failure(str(R.string.nfc_write_failed, result.message))
        }
    }

    private fun runRead(card: MifareCard) {
        progress(str(R.string.nfc_reading))
        val keys = BambuKeys.derive(card.uid)
        val dump = cloner.readDump(card, keys)
        if (dump == null || !DumpValidator.validate(dump).ok) {
            failure(str(R.string.read_not_bambu))
            return
        }
        set { it.copy(status = OpStatus.ReadDone(FilamentInfo.parse(dump))) }
    }

    private fun runCuidCheck(card: MifareCard) {
        progress(str(R.string.nfc_reading))
        when (cloner.checkCuid(card)) {
            CuidCheck.Writable -> success(str(R.string.cuid_writable))
            CuidCheck.NotWritable -> failure(str(R.string.cuid_not_writable))
            CuidCheck.NeedsFormat -> failure(str(R.string.cuid_needs_format))
            is CuidCheck.Error -> failure(str(R.string.nfc_read_failed, "카드 점검"))
        }
    }

    private fun progress(msg: String) = set { it.copy(status = OpStatus.Progress(msg)) }

    private fun success(msg: String) = set { it.copy(status = OpStatus.Success(msg)) }

    private fun failure(msg: String) = set { it.copy(status = OpStatus.Failure(msg)) }

    private fun str(resId: Int, vararg args: Any): String =
        getApplication<Application>().getString(resId, *args)

    private companion object {
        const val KEY_SKIPPED = "skipped_commit"
    }
}
