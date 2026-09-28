package com.ams.rfid.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ams.rfid.R
import com.ams.rfid.core.FilamentInfo
import com.ams.rfid.core.LibraryUpdate
import com.ams.rfid.data.EntryInfo
import com.ams.rfid.data.FilamentEntry
import com.ams.rfid.data.FilamentLibrary
import com.ams.rfid.data.LibrarySource

private fun parseColor(hex: String?): Color {
    if (hex == null) return Color.Gray
    return try {
        val h = hex.removePrefix("#").let { if (it.length >= 6) it.substring(0, 6) else it }
        Color(android.graphics.Color.parseColor("#$h"))
    } catch (e: Exception) {
        Color.Gray
    }
}

@Composable
fun AppRoot(vm: MainViewModel) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    Scaffold(
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = ui.tab == Tab.LIBRARY,
                    onClick = { vm.setTab(Tab.LIBRARY) },
                    icon = { Icon(Icons.Filled.List, null) },
                    label = { Text(stringResource(R.string.tab_library)) },
                )
                NavigationBarItem(
                    selected = ui.tab == Tab.READ,
                    onClick = { vm.setTab(Tab.READ) },
                    icon = { Icon(Icons.Filled.Search, null) },
                    label = { Text(stringResource(R.string.tab_read)) },
                )
                NavigationBarItem(
                    selected = ui.tab == Tab.HELP,
                    onClick = { vm.setTab(Tab.HELP) },
                    icon = { Icon(Icons.Filled.Info, null) },
                    label = { Text(stringResource(R.string.tab_help)) },
                )
            }
        },
    ) { pad ->
        Box(Modifier.padding(pad).fillMaxSize()) {
            when (ui.tab) {
                Tab.LIBRARY -> LibraryScreen(ui, vm)
                Tab.READ -> ReadScreen(vm)
                Tab.HELP -> HelpScreen(ui, vm)
            }
        }
    }
    ui.selected?.let { DetailSheet(it, vm) }
    if (ui.showSheet) OperationSheet(ui, vm)
    UpdateDialog(ui, vm)
}

@Composable
private fun LibraryScreen(ui: UiState, vm: MainViewModel) {
    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = ui.query,
            onValueChange = vm::setQuery,
            leadingIcon = { Icon(Icons.Filled.Search, null) },
            placeholder = { Text(stringResource(R.string.search_hint)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(12.dp),
        )
        when (val lib = ui.library) {
            is LibraryState.Loading -> CenterProgress()
            is LibraryState.Error -> CenterText(lib.message)
            is LibraryState.Ready -> {
                Text(
                    text = stringResource(R.string.library_count, ui.results.size),
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
                if (ui.results.isEmpty()) {
                    CenterText(stringResource(R.string.library_empty))
                } else {
                    LazyColumn(
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(ui.results, key = { it.searchKey }) { entry ->
                            EntryRow(entry) { vm.select(entry) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EntryRow(entry: FilamentEntry, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clickable { onClick() }) {
        Row(
            Modifier.padding(12.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ColorSwatch(entry.info)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(entry.color, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    entry.material,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Text(
                stringResource(R.string.samples_count, entry.samples.size),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.outline,
            )
        }
    }
}

@Composable
private fun ColorSwatch(info: EntryInfo?, size: Int = 40) {
    val c1 = parseColor(info?.colorHex)
    val c2 = info?.color2Hex?.let { parseColor(it) }
    Box(
        Modifier
            .size(size.dp)
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, CircleShape)
            .background(c1, CircleShape),
    ) {
        if (c2 != null) {
            Box(Modifier.fillMaxSize()) {
                Box(
                    Modifier
                        .fillMaxWidth(0.5f)
                        .fillMaxSize()
                        .background(c2),
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DetailSheet(entry: FilamentEntry, vm: MainViewModel) {
    ModalBottomSheet(onDismissRequest = { vm.select(null) }) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ColorSwatch(entry.info, size = 56)
                Spacer(Modifier.width(16.dp))
                Column {
                    Text(entry.color, style = MaterialTheme.typography.titleLarge)
                    Text(entry.material, style = MaterialTheme.typography.bodyMedium)
                }
            }
            Spacer(Modifier.height(16.dp))
            entry.info?.let { i ->
                InfoLine(stringResource(R.string.detail_type, i.detailType.ifEmpty { i.type }))
                InfoLine(stringResource(R.string.detail_weight, i.weightGram))
                InfoLine(stringResource(R.string.detail_diameter, i.diameterMm))
                InfoLine(stringResource(R.string.detail_hotend, i.minHotendC, i.maxHotendC))
                InfoLine(stringResource(R.string.detail_bed, i.bedTempC))
            }
            Spacer(Modifier.height(20.dp))
            Button(
                onClick = { vm.armWrite(entry) },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.detail_write_button))
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

@Composable
private fun ReadScreen(vm: MainViewModel) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(stringResource(R.string.read_intro), style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(24.dp))
        Button(onClick = { vm.armRead() }, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.read_start))
        }
        Spacer(Modifier.height(12.dp))
        OutlinedButton(onClick = { vm.armCuidCheck() }, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.cuid_check))
        }
        Spacer(Modifier.height(8.dp))
        Text(
            stringResource(R.string.cuid_check_warning),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.error,
        )
    }
}

@Composable
private fun HelpScreen(ui: UiState, vm: MainViewModel) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
    ) {
        (ui.library as? LibraryState.Ready)?.library?.let { DbCard(it, ui.update, vm) }
        Spacer(Modifier.height(20.dp))
        Text(stringResource(R.string.help_title), style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(12.dp))
        Text(stringResource(R.string.help_body), style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(16.dp))
        Divider()
        Spacer(Modifier.height(16.dp))
        Text(
            stringResource(R.string.help_disclaimer),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline,
        )
    }
}

/** 현재 필라멘트 DB 정보와 수동 업데이트 확인 버튼. */
@Composable
private fun DbCard(library: FilamentLibrary, update: UpdateState, vm: MainViewModel) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(stringResource(R.string.db_title), style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            InfoLine(stringResource(R.string.db_summary, library.entries.size, library.sampleCount))
            InfoLine(stringResource(R.string.db_version, library.commit.take(7), library.generated.take(10)))
            InfoLine(
                stringResource(
                    if (library.source == LibrarySource.DOWNLOADED) R.string.db_source_downloaded
                    else R.string.db_source_bundled,
                ),
            )
            Spacer(Modifier.height(12.dp))
            val busy = update is UpdateState.Checking || update is UpdateState.Downloading
            OutlinedButton(
                onClick = { vm.checkForUpdate(manual = true) },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (busy) {
                    CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text(stringResource(R.string.db_checking))
                } else {
                    Text(stringResource(R.string.db_check))
                }
            }
        }
    }
}

/** 새 DB가 있을 때 업데이트할지 묻고, 진행/결과를 보여주는 다이얼로그. */
@Composable
private fun UpdateDialog(ui: UiState, vm: MainViewModel) {
    when (val u = ui.update) {
        is UpdateState.Available -> {
            val current = (ui.library as? LibraryState.Ready)?.library ?: return
            AlertDialog(
                onDismissRequest = { vm.postponeUpdate() },
                title = { Text(stringResource(R.string.db_update_title)) },
                text = {
                    Text(
                        stringResource(
                            R.string.db_update_body,
                            current.entries.size,
                            current.generated.take(10),
                            u.manifest.colors,
                            u.manifest.generated.take(10),
                            changesText(u.diff),
                        ),
                    )
                },
                confirmButton = {
                    TextButton(onClick = { vm.applyUpdate() }) { Text(stringResource(R.string.db_update_now)) }
                },
                dismissButton = {
                    TextButton(onClick = { vm.postponeUpdate() }) { Text(stringResource(R.string.db_update_later)) }
                },
            )
        }
        is UpdateState.Downloading -> AlertDialog(
            onDismissRequest = {},
            title = { Text(stringResource(R.string.db_update_title)) },
            text = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(24.dp))
                    Spacer(Modifier.width(16.dp))
                    Text(stringResource(R.string.db_downloading))
                }
            },
            confirmButton = {},
        )
        is UpdateState.Message -> AlertDialog(
            onDismissRequest = { vm.dismissUpdateMessage() },
            text = { Text(u.text) },
            confirmButton = {
                TextButton(onClick = { vm.dismissUpdateMessage() }) { Text(stringResource(R.string.ok)) }
            },
        )
        UpdateState.Idle, UpdateState.Checking -> {}
    }
}

/** 추가/삭제된 색상 요약 문구. */
@Composable
private fun changesText(diff: LibraryUpdate.Diff): String {
    val lines = mutableListOf<String>()
    if (diff.added.isNotEmpty()) {
        val names = diff.added.take(3).joinToString(", ") { LibraryUpdate.displayName(it) }
        lines += if (diff.added.size > 3) {
            stringResource(R.string.db_update_added_more, names, diff.added.size - 3)
        } else {
            stringResource(R.string.db_update_added, names)
        }
    }
    if (diff.removed.isNotEmpty()) {
        lines += stringResource(R.string.db_update_removed, diff.removed.size)
    }
    if (lines.isEmpty()) lines += stringResource(R.string.db_update_data_only)
    return lines.joinToString("\n")
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun OperationSheet(ui: UiState, vm: MainViewModel) {
    ModalBottomSheet(onDismissRequest = {
        // 진행 중에는 닫아도 작업 자체는 콜백에서 계속되지만, UI 상태만 초기화한다.
        vm.dismissSheet()
    }) {
        Column(
            Modifier.fillMaxWidth().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            when (val s = ui.status) {
                is OpStatus.Idle -> {
                    val prompt = when (ui.armed) {
                        is Armed.Write -> stringResource(R.string.nfc_prompt_write)
                        else -> stringResource(R.string.nfc_prompt_read)
                    }
                    CircularProgressIndicator()
                    Spacer(Modifier.height(16.dp))
                    Text(prompt, style = MaterialTheme.typography.titleMedium)
                }
                is OpStatus.Progress -> {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                    Spacer(Modifier.height(16.dp))
                    Text(s.message, style = MaterialTheme.typography.titleMedium)
                }
                is OpStatus.Success -> ResultBlock(true, s.message, vm)
                is OpStatus.Failure -> ResultBlock(false, s.message, vm)
                is OpStatus.ReadDone -> ReadResultBlock(s.info, vm)
            }
        }
    }
}

@Composable
private fun ResultBlock(success: Boolean, message: String, vm: MainViewModel) {
    Text(
        text = if (success) "✅" else "⚠️",
        style = MaterialTheme.typography.displaySmall,
    )
    Spacer(Modifier.height(12.dp))
    Text(message, style = MaterialTheme.typography.titleMedium)
    Spacer(Modifier.height(20.dp))
    Button(onClick = { vm.dismissSheet() }, modifier = Modifier.fillMaxWidth()) {
        Text(stringResource(R.string.close))
    }
}

@Composable
private fun ReadResultBlock(info: FilamentInfo, vm: MainViewModel) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(48.dp)
                .background(parseColor(info.colorHex), CircleShape)
                .border(1.dp, MaterialTheme.colorScheme.outlineVariant, CircleShape),
        )
        Spacer(Modifier.width(16.dp))
        Column {
            Text(info.detailedType.ifEmpty { info.filamentType }, style = MaterialTheme.typography.titleMedium)
            Text(stringResource(R.string.detail_uid, info.uid), style = MaterialTheme.typography.bodySmall)
        }
    }
    Spacer(Modifier.height(16.dp))
    InfoLine(stringResource(R.string.detail_weight, info.spoolWeightGram))
    InfoLine(stringResource(R.string.detail_diameter, info.diameterMm))
    InfoLine(stringResource(R.string.detail_hotend, info.minHotendC, info.maxHotendC))
    InfoLine(stringResource(R.string.detail_bed, info.bedTempC))
    InfoLine(stringResource(R.string.detail_drying, info.dryingTempC, info.dryingTimeH))
    if (info.productionDate.isNotBlank()) {
        InfoLine(stringResource(R.string.detail_production, info.productionDate))
    }
    Spacer(Modifier.height(20.dp))
    Button(onClick = { vm.dismissSheet() }, modifier = Modifier.fillMaxWidth()) {
        Text(stringResource(R.string.close))
    }
}

@Composable
private fun InfoLine(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 2.dp))
}

@Composable
private fun CenterProgress() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
}

@Composable
private fun CenterText(text: String) {
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Text(text, style = MaterialTheme.typography.bodyLarge)
    }
}
