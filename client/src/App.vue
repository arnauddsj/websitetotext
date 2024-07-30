<script setup lang="ts">
import { ref, onMounted, shallowRef, computed } from "vue";
import axios from "axios";
import { EditorView, basicSetup } from "codemirror";
import { json } from "@codemirror/lang-json";
import { EditorState } from "@codemirror/state";
import { lineNumbers } from "@codemirror/view";
import { oneDark } from "@codemirror/theme-one-dark";
import DOMPurify from "dompurify";

interface CrawlResult {
  pages: Array<{
    content: {
      h1?: string[];
      h2?: string[];
      h3?: string[];
      h4?: string[];
      text?: string[];
    };
  }>;
}

const url = ref("");
const maxPages = ref(10);
const MAX_CRAWL_PAGES = 100;
const displayMaxPages = ref(maxPages.value.toString());
const result = ref<CrawlResult | null>(null);
const loading = ref(false);
const editorElement = ref(null);
const editorView = shallowRef<EditorView | null>(null);
const httpWarning = ref(false);

const normalizedUrl = computed(() => {
  let normalizedUrl = url.value.trim().toLowerCase();
  if (!normalizedUrl.startsWith("http://") && !normalizedUrl.startsWith("https://")) {
    normalizedUrl = "https://" + normalizedUrl;
  }
  return normalizedUrl;
});

const isValidUrl = computed(() => {
  try {
    new URL(normalizedUrl.value);
    return true;
  } catch {
    return false;
  }
});

const isValidMaxPages = computed(() => {
  return Number.isInteger(maxPages.value) && maxPages.value > 0;
});

const canCrawl = computed(() => isValidUrl.value && isValidMaxPages.value);

const handleKeyPress = (event: KeyboardEvent) => {
  if (event.key === "Enter") {
    crawlWebsite();
  }
};

const sanitizeContent = (content: string) => {
  return DOMPurify.sanitize(content);
};

const lastCrawlTime = ref(0);
const CRAWL_COOLDOWN = 5000; // 5 seconds

const updateMaxPages = () => {
  const parsed = parseInt(displayMaxPages.value, 10);
  if (!isNaN(parsed)) {
    maxPages.value = Math.min(parsed, MAX_CRAWL_PAGES);
  }
  displayMaxPages.value = maxPages.value.toString();
};

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

  if (editorElement.value) {
    editorView.value = new EditorView({
      state,
      parent: editorElement.value,
    });
  }
});

axios.defaults.withCredentials = true;

const crawlWebsite = async () => {
  const now = Date.now();
  if (now - lastCrawlTime.value < CRAWL_COOLDOWN) {
    alert(
      `Please wait ${Math.ceil(
        (CRAWL_COOLDOWN - (now - lastCrawlTime.value)) / 1000
      )} seconds before crawling again.`
    );
    return;
  }

  lastCrawlTime.value = now;

  if (!canCrawl.value) {
    alert(`Please enter a valid URL and number of pages (1-${MAX_CRAWL_PAGES}).`);
    return;
  }
  loading.value = true;
  try {
    console.log("Crawling URL:", normalizedUrl.value);
    const response = await axios.post(
      `${import.meta.env.VITE_API_URL}/crawl`,
      {
        url: normalizedUrl.value,
        max_pages: maxPages.value,
      },
      {
        headers: {
          "X-CSRF-TOKEN":
            document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
            "",
        },
      }
    );
    result.value = response.data;

    // Update the editor content
    if (editorView.value) {
      const jsonString = JSON.stringify(result.value, null, 2);
      editorView.value.dispatch({
        changes: {
          from: 0,
          to: editorView.value.state.doc.length,
          insert: sanitizeContent(jsonString),
        },
      });
    }
  } catch (error) {
    console.error("Error:", error);
    alert("An error occurred while crawling the website. Please try again later.");
  } finally {
    loading.value = false;
  }
};

const downloadJSON = () => {
  if (!editorView.value) return;
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

const convertToTxt = () => {
  console.log("Converting to TXT, result:", result.value);

  if (!result.value || !Array.isArray(result.value.pages)) {
    console.error("Invalid result structure:", result.value);
    alert("The data structure is not in the expected format.");
    return;
  }

  const content = result.value.pages.flatMap((page) => {
    if (!page || typeof page.content !== "object") return [];

    const headers = ["h1", "h2", "h3", "h4"].flatMap((h) =>
      Array.isArray(page.content[h as keyof typeof page.content])
        ? page.content[h as keyof typeof page.content]
        : []
    );
    const text = Array.isArray(page.content.text) ? page.content.text : [];
    return [...headers, ...text];
  });

  console.log("Processed content:", content);

  const txtContent = content.join("\n\n");

  console.log("Final TXT content length:", txtContent.length);

  // Use the Blob API for better cross-browser compatibility
  const blob = new Blob([txtContent], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = "crawl_result.txt";
  a.style.display = "none";
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
      <input
        v-model="url"
        placeholder="Enter website URL (e.g., example.com)"
        @keyup.enter="handleKeyPress"
      />
      <input
        v-model="displayMaxPages"
        type="number"
        :placeholder="`Max pages to crawl (1-${MAX_CRAWL_PAGES})`"
        @input="updateMaxPages"
      />
      <button @click="crawlWebsite" :disabled="loading || !canCrawl">
        {{ loading ? "Crawling..." : "Crawl Website" }}
      </button>
      <button @click="downloadJSON" :disabled="!result">Download JSON</button>
      <button @click="convertToTxt" :disabled="!result">Download TXT</button>
    </div>
    <div v-if="httpWarning" class="warning">
      <!-- Your warning message about HTTP -->
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
.warning {
  color: #ff9800;
  margin-bottom: 10px;
}
</style>
