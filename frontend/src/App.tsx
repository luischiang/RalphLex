import { BrowserRouter, Route, Routes } from "react-router-dom";
import Nav from "./components/Nav";
import CaseDetail from "./pages/CaseDetail";
import CaseList from "./pages/CaseList";
import CaseSubmit from "./pages/CaseSubmit";
import Monitor from "./pages/Monitor";

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        <Nav />
        <main className="mx-auto max-w-5xl px-4 py-8">
          <Routes>
            <Route path="/" element={<CaseList />} />
            <Route path="/submit" element={<CaseSubmit />} />
            <Route path="/cases/:caseId" element={<CaseDetail />} />
            <Route path="/monitor" element={<Monitor />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
