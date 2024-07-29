<script setup lang="ts">
import { ref, onMounted, shallowRef } from "vue";
import axios from "axios";
import { EditorView, basicSetup } from "codemirror";
import { json } from "@codemirror/lang-json";
import { EditorState } from "@codemirror/state";
import { lineNumbers } from "@codemirror/view";
import { oneDark } from "@codemirror/theme-one-dark";

const url = ref("");
const maxPages = ref(10);
const result = ref(null);
const loading = ref(false);
const editorElement = ref(null);
const editorView = shallowRef(null);

onMounted(() => {
  const state = EditorState.create({
    doc: "",
    extensions: [
      basicSetup,
      json(),
      lineNumbers(),
      EditorView.lineWrapping,
      oneDark,
      EditorView.theme({
        "&": { height: "100%" },
        ".cm-scroller": { overflow: "auto" },
        ".cm-content": {
          fontFamily: "monospace",
          textAlign: "left",
        },
        ".cm-line": {
          padding: "0 4px",
          textAlign: "left",
        },
      }),
      EditorView.updateListener.of((v) => {
        if (v.docChanged) {
          // Handle document changes if needed
        }
      }),
    ],
  });

  editorView.value = new EditorView({
    state,
    parent: editorElement.value,
  });
});

const crawlWebsite = async () => {
  loading.value = true;
  try {
    const response = await axios.post("http://localhost:8000/crawl", {
      url: url.value,
      max_pages: maxPages.value,
    });
    result.value = response.data;

    // Update the editor content
    const jsonString = JSON.stringify(result.value, null, 2);
    editorView.value.dispatch({
      changes: { from: 0, to: editorView.value.state.doc.length, insert: jsonString },
    });
  } catch (error) {
    console.error("Error:", error);
    alert("An error occurred while crawling the website.");
  } finally {
    loading.value = false;
  }
};

const downloadJSON = () => {
  const jsonString = editorView.value.state.doc.toString();
  const blob = new Blob([jsonString], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "crawl_result.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};
</script>

<template>
  <div class="container">
    <h1>Website Crawler</h1>
    <div class="input-group">
      <input v-model="url" placeholder="Enter website URL" />
      <input v-model="maxPages" type="number" placeholder="Max pages to crawl" />
      <button @click="crawlWebsite" :disabled="loading">
        {{ loading ? "Crawling..." : "Crawl Website" }}
      </button>
      <button @click="downloadJSON" :disabled="!result">Download JSON</button>
    </div>
    <div class="editor-container" ref="editorElement"></div>
  </div>
</template>

<style scoped>
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}
.input-group {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.input-group input {
  flex-grow: 1;
}
.editor-container {
  height: 600px;
  border: 1px solid #ccc;
}
:deep(.cm-editor) {
  height: 100%;
  font-size: 14px;
}
:deep(.cm-content),
:deep(.cm-line) {
  text-align: left !important;
}
:deep(.cm-activeLineGutter) {
  background-color: rgba(255, 255, 255, 0.1);
}
</style>
